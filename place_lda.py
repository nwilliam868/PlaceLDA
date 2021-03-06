#-------------------------------------------------------------------------------
# Name:        Place Topic Modeller
# Purpose:     This program can be used to:
#               - (constructTrainingData()): extract, for a list of places (identified by OSM ids) given in a csv file,
#                the webtexts from corresponding websites (given as input) and social media posts (Google places, automatically linked)
#               - (trainLDA()): Build a topic model (with Latent Dirichlet Allocation) from these webtexts and put topics together with
#               place tags (OSM, Google) into feature vectors for data mining
#               - (classify()): Run and test different classifiers on these features to predict a given class label that stands for explicit predefined
#               topics (e.g. place types or activities at places).
#
# Author:      Simon Scheider Ben Adams
#
# Created:     22/08/2017
# Copyright:   (c) simon 2017
# Licence:     <your licence>
#-------------------------------------------------------------------------------
from __future__ import division, print_function
#Libraries:

#Numpy and matplotlib:
import numpy as np
import matplotlib.pyplot as plt

#This connects to the Open Street Map API Overpass
import overpy
#This is the Google places API
from googleplaces import GooglePlaces, types, lang, GooglePlacesError

#This is a webscraper I use as an external tool (loaded as file in the same folder)
import placewebscraper

from collections import Counter


#This is the LDA Python library for topic modeling
import lda


import sys
#This is just for me to prevent installing the LLDA module locally
sys.path.append("C:/Users/simon/Documents/GitHub/PlaceLDA")

#This is the Labeled LDA (LLDA) Python library
from LLDA.llda import LLDAClassifier
# LLDA uses gensim corpus format
from gensim import corpora

#Use NLTK for preprocessing webtexts
import nltk
from nltk.corpus import stopwords
from nltk.stem.porter import PorterStemmer
from nltk.stem.snowball import DutchStemmer

#Machine Learning classifiers (scikit learn)
#Scikit learn preprocessing
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.preprocessing import Normalizer
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn import metrics
from sklearn.model_selection import train_test_split
from sklearn.model_selection import cross_val_score
from sklearn.metrics import confusion_matrix, accuracy_score, precision_recall_fscore_support, coverage_error, hamming_loss, jaccard_similarity_score
from sklearn.dummy import DummyClassifier
#This is used to deal with categorial input instead of numerical
from sklearn.feature_extraction import DictVectorizer
#These are the classifiers used
from sklearn.neural_network import MLPClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.gaussian_process.kernels import RBF
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, AdaBoostClassifier
from sklearn.naive_bayes import GaussianNB
#from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression

#Classifiers for multi label
from sklearn.multiclass import OneVsRestClassifier
#pip install scikit-multilearn
#from skmultilearn.problem_transform import BinaryRelevance, ClassifierChain, LabelPowerset
#from skmultilearn.adapt import MLkNN

 #from    sklearn.tree import DecisionTreeClassifier
from    sklearn.tree import ExtraTreeClassifier
from    sklearn.ensemble import ExtraTreesClassifier
#from    sklearn.neighbors import KNeighborsClassifier
from   sklearn.neural_network import MLPClassifier
from    sklearn.neighbors import RadiusNeighborsClassifier
from    sklearn.ensemble import RandomForestClassifier
from    sklearn.linear_model import RidgeClassifierCV


#Somegeo stuff
from shapely.geometry import mapping, Point
import fiona

#Non-essential libraries:

import string
import itertools
import sys
import csv
import os
import json
from random import randint
from time import sleep

import re









#This the Google key that I use
YOUR_API_KEY = 'AIzaSyA2O6G7eCxOFTbu1HjPuqpuLEnllSDQDB8'

def matchtoGoogleP(placename,lat, lng):
    """ Method matches a placename and its coordinates (WGS84) to a corresponding place from Google API """
    lat_lng = {}
    lat_lng['lat']=lat
    lat_lng['lng']=lng
    google_places = GooglePlaces(YOUR_API_KEY)
    place = None
    try:
        query_result = google_places.text_search(placename,lat_lng,radius=300)
    #if query_result.has_attributions:
        #    print query_result.html_attributions
        if len(query_result.places)>0:
            place = query_result.places[0]
            place.get_details()
    except GooglePlacesError as error_detail:
    # You've passed in parameter values that the Places API doesn't like..
        print(error_detail)
        sleep(3)
        #query_result = google_places.text_search(placename,lat_lng,radius=300)
    #if query_result.has_attributions:
        #    print query_result.html_attributions
        return place

    # The following method has to make a further API call.

    # Referencing any of the attributes below, prior to making a call to
    # get_details() will raise a googleplaces.GooglePlacesAttributeError.
    ##    print place.details # A dict matching the JSON response from Google.
##    print place.website
##    print place.types
##    print place.details['opening_hours']
##    #print place.details['reviews']
##    if 'reviews' in place.details.keys():
##        for r in place.details['reviews']:
##            print r['text']
##    print place.rating

    return place

def getCentroid(nodes):
    points = [(n.lon,n.lat) for n in nodes]
    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]
    _len = len(points)
    centroid_x = sum(x_coords)/_len
    centroid_y = sum(y_coords)/_len
    return (centroid_x, centroid_y)

#The keys of interest are OSM keys (tags) that are of interest to describe a place type. These keys will be fetched from OSM
keysofinterest = ['shop', 'amenity', 'leisure', 'tourism', 'historic', 'man_made', 'tower', 'cuisine', 'clothes', 'tower', 'beer', 'highway', 'surface', 'place', 'building']

def getOSMInfo(osmid, elementtype='node'):
    """ Method fetches additional information (tags) of a given OSM object from the Overpass API """
    api = overpy.Overpass()
    osm = {}
    try:
        try:
            result = api.query((elementtype+"({}); out;").format(osmid))
        except overpy.exception.OverpassGatewayTimeout as error_detail:
            print(error_detail)
            #This prevents gateway timeouts
            sleep(20)
            result = api.query((elementtype+"({}); out;").format(osmid))
        except overpy.exception.OverpassTooManyRequests as error_detail:
            sleep(30)
            result = api.query((elementtype+"({}); out;").format(osmid))
        if elementtype == 'node':
            res = result.get_node(osmid,resolve_missing=True)
            osm['lat'] = res.lat
            osm['lon'] = res.lon
        elif elementtype == 'way':
            res = result.get_way(osmid,resolve_missing=True)
            try:
                c = getCentroid(res.get_nodes(resolve_missing=True))
            except overpy.exception.OverpassTooManyRequests as error_detail:
                sleep(30)
                c = getCentroid(res.get_nodes(resolve_missing=True))
            osm['lat']=c[1]
            osm['lon']=c[0]

    except overpy.exception.DataIncomplete as error_detail:
    # You've passed in parameter values that the Places API doesn't like..
        print(error_detail)
        return None
    except overpy.exception.OverpassGatewayTimeout as error_detail:
        print(error_detail)
        sleep(20)
        return None

    #print(res.attributes)
    if 'name' in res.tags:
        osm['name'] = res.tags['name']
        osm['keys'] = []
        #Get the relevant tags if they exist
        for k,v in res.tags.items():
                if k in keysofinterest:
                    osm[k]= v
        if 'website' in res.tags.keys():
                osm['website'] = res.tags['website']
        if 'opening_hours' in res.tags.keys():
                osm['opening_hours'] = res.tags['opening_hours']
        #print(osm)
        return osm
    else:
        return None



def enrichOSM(osmid,elementtype,website=None):
    """ Method enriches a given OSM object with information from webtexts from some given webiste, with OSM tags, Google place tags, Google reviewtexts and webtexts based on the Google weblink"""
    osmid = int(osmid)

    print('enrich: '+elementtype+' '+str(osmid))
    enriched = {}

    #Print(Putting computer to sleep for 3 seconds after each request to prevent OSM server overload:
    sleep(randint(3,6))

    #First get the text from the website if it exists
    if (website!=None):
        wt = placewebscraper.scrape(website)
        if wt !=None:
            enriched['webtext']= wt['text']
            enriched['webtitle'] = wt['title']
        enriched['website']=website
    #Get additonal OSM info
    osm = getOSMInfo(osmid, os.path.basename(elementtype))
    if osm == None:
        return enriched
    #print(osm)
    enriched['name']= osm['name']
    print(osm['name'])
    for k in keysofinterest:
        if k in osm.keys():
            enriched[k]=osm[k]
        else:
            enriched[k] = 'No'
    #enriched['osmtype']='|'.join(sorted(osm['keys']))
    enriched['lat']=str(osm['lat'])
    enriched['lon']=str(osm['lon'])
    place = matchtoGoogleP(osm['name'],osm['lat'],osm['lon'])
    if place == None:
        return enriched
    try:
        place.get_details()
    except GooglePlacesError as error_detail:
    # You've passed in parameter values that the Places API doesn't like..
        print(error_detail)
        return enriched

    enriched['GoogleId'] = place.place_id
    #print(place.details)
    #This is the webiste delivered as input to the funtion

    #This is the google website
##    if place.website != None:
##        wt = placewebscraper.scrape(place.website)
##        if wt !=None:
##            enriched['gwebtext']= wt['text']
##            enriched['gwebtitle'] = wt['title']
##        enriched['gwebsite']=place.website
    enriched['googletype'] ='|'.join(sorted(place.types))
    #print place.details['opening_hours']
    #print place.details['reviews']
    if 'reviews' in place.details.keys():
        text= ' '.join([r['text']+' ' for r in place.details['reviews']])
        text = text.replace('\n', ' ').replace('\r', '')
        text = re.sub(r'[?|$|.|!]',r'',text)
        text = re.sub(r'[^a-zA-Z]',r' ',text)
        enriched['reviewtext'] = text
    return enriched


def countPlaces(filename):
    pass


def constructTrainingData(filename, write=True):
    """ Method constructs training data by first reading a list of labeled OSM ids, then enriching them with web information.
        Result is stored in a json file at the same place as the input file."""
    #from pprint import pprint
    td = {}
    #Reads in the csv file of class labeled place ids
    with open(filename, 'rb') as csvfile:
        reader = csv.reader(csvfile, delimiter=',', quotechar='|')
        out = (os.path.splitext(os.path.basename(filename))[0][:9])+'_train.json'
        rr = {}
        for i,line in enumerate(reader):
                #line = line.rstrip('\r\n').split("\t")
                if i >0:
                    #print(line)
                    osmid = line[0].split(':')[1]
                    if (line[0].split(':')[0]== 'osm'):
                        elementtype = 'https://www.openstreetmap.org/node'
                    elif (line[0].split(':')[0]== 'osmw'):
                        elementtype = 'https://www.openstreetmap.org/way'
                    else:
                        print("Error: not node or way!")
                        break
                    #Fishes out place activity and referent and combines them
                    classstr = '|'.join([line[2].decode('unicode_escape').encode('utf-8'),line[3].decode('unicode_escape').encode('utf-8')])
                    name = line[1].decode('unicode_escape').encode('utf-8')
                    d = {'osmid': osmid, 'class': [classstr],'elementtype':elementtype, 'uloplace': line[4].decode('unicode_escape').encode('utf-8'), 'website':line[5], 'name':name}
                    #collect different classes of the same osm object into an array
                    if line[0] in rr.keys():
                        rr[line[0]]['class'].append(classstr)
                    else:
                        rr[line[0]] = d

        print('Length of the array read : '+str(len(rr))+' number of rows read '+str(i))

        if write == True:
            #Writes out the json file and does the enrichment in a manner that each OSM id is queried only once
            with open(out, 'w') as fp:
                for k,v in rr.items():
                        osmid = v['osmid']
                        website = v['website']
                        elementtype = v['elementtype']
                        en = enrichOSM(osmid,elementtype,website)
                        print(osmid)
                        print('enriched properties: '+str(en.keys()))
                        enn = en.copy()
                        enn['osmid'] = osmid
                        enn['name'] = v['name']
                        enn['uloplace'] = v['uloplace']
                        enn['class']= v['class']
                        print(v['class'])
                        enn['website'] = v['website']
                        td[k] = enn
                        print("number of successul enrichments: "+str(len(td)))
                        fp.seek(0)
                        json.dump(td, fp)
            fp.close()
    csvfile.close()
    #pprint(td)


def tokenize(text, language = 'dutch'):
    """ Method turns a text into tokens removing stopwords and stemming them."""
    if language == 'dutch':
        p_stemmer = DutchStemmer()
    else:
        p_stemmer = PorterStemmer()

    text = text.lower()
    stop = set(stopwords.words(language))
    tokens = nltk.word_tokenize(text)
    tokens = [i for i in tokens if i not in string.punctuation and len(i)>=3]
    tokens = [i for i in tokens if i not in stop]
    tokens = [i for i in tokens if i.isalpha()]
    tokens = [p_stemmer.stem(i) for i in tokens]
    return tokens

def trainLDA(jsonfile, textkey, textkey2='gwebtext', language='dutch', usetopics=True, usetypes=True,  actlevel = True, minclasssize = 0, multilabel=False):
    """ Method takes the enriched json file (training data), and builds an LDA topic model.
     It trains an LDA topic model on the webtexts, puts everything together in feature vectors and returns this together with the classes as two simple arrays
    Usetypes = True puts also OSMtags and GooglePlace tags into the feature vector, in addition to topics. actlevel = True restricts classes to the activity level (no referent classes).
    Minclasssize filters out too small classes. Multilabel = True means that multiple labels (classes) are allowed per osm place"""
    texts = [] #array that holds the LDA text documents
    titles = [] #array that holds the titles of documents (in this case place names)
    classes = [] #array that holds the goal classes
    features = [] #array the holds the feature vectors
    geoinfo = [] #stuf needed to map results

    #testclasses = ['ulo:Eating|ulo:Food']
    with open(jsonfile) as json_data:
        d = json.load(json_data)
        print('Size of the json file: '+str(len(d)))

        #first determine the class frequencies of all classes occurring
        classbag = []
        for k,v in d.items():
            for c in v['class']:
                if actlevel:
                    cl = c.split('|')[0]
                else:
                    cl = c
                classbag.append(cl)
        clfreq = Counter(classbag)
        print(clfreq)
        #print(clfreq['ulo:Eating'])

        listofosmids = []
        #print(d)
        for k,v in d.items():
          #Collect features for each osm id. Take only a single goal class fo reach osm id
          if not ( v['osmid'] in listofosmids):
            gtext = ''
            wtext = ''
            if textkey2 in v.keys():
                gtext =v[textkey2]
            if textkey in v.keys():# and 'googletype' in (d[k]).keys():
                wtext =v[textkey]
            if 'reviewtext' in v.keys():
                rtext =v['reviewtext']
            text = (wtext if wtext !='' else ( gtext if gtext != '' else ''))
            if text != '':
                listofosmids.append(v['osmid'])
                texts.append(text)
                titles.append(v['name'])
                dd = {'osmid':k,'name':v['name']}
                if 'lat' in v.keys():
                    dd['lat']=v['lat']
                    dd['lon']=v['lon']
                geoinfo.append(dd)

                if multilabel == False:
                    #select the class that occurs most frequently over all places as the class of an osm id
                    classize = 0
                    cl = None
                    for c in v['class']:
                        if actlevel:
                            x = c.split('|')[0]
                        else:
                            x = c
                        if clfreq[x]>classize:
                            cl = x
                            classize =clfreq[x]
                    classes.append(cl)
                else:
                    #add all classes of a place in terms of an array
                    cls = []
                    for c in v['class']:
                        if actlevel:
                            x = c.split('|')[0]
                        else:
                            x = c
                        cls.append(x)
                    classes.append(cls)

                dic = {}
                #Add the place tags from OSM or GooglePlaces
                if usetypes == True:
                    if 'googletype' in v.keys():
                        dic['googletype'] =v['googletype']
                    #dic['osmtype'] =v['osmtype']
                    for typekey in keysofinterest:
                        if typekey in v.keys():
                            dic[typekey] = v[typekey]
                        else:
                            dic[typekey] = 'No'
                features.append(dic)


    json_data.close

    #This is where the texts get turned into a document-term matrix
    vectorizer = CountVectorizer(min_df = 1, stop_words = stopwords.words(language), analyzer = 'word', tokenizer=tokenize)
    X = vectorizer.fit_transform(texts)
    #print(X)
    #Gets the vocabulary of stemmed words (terms)
    vocab = vectorizer.get_feature_names()
    print(vocab)
    #This computes the LDA model
    model = lda.LDA(n_topics=18, n_iter=600, random_state=300)
    model.fit(X)
    topic_word = model.topic_word_
    #print("type(topic_word): {}".format(type(topic_word)))
    print("shape: {}".format(topic_word.shape))

    # get the top 5 words for each topic (by probablity)
    n = 5
    c = 0
    for i, topic_dist in enumerate(topic_word):
        topic_words = np.array(vocab)[np.argsort(topic_dist)][:-(n+1):-1]
        print('*Topic {}\n- {}'.format(i, ' '.join(topic_words)))
        c += 1
    #return model
    # apply topic model to new test data set and write topics into feature vector
    doc_topic_test = model.transform(X)
    #print(doc_topic_test)
    i = 0
    for title, topics in zip(titles, doc_topic_test):
        title =title.encode('utf-8')
        print("{} (top topic: {})".format(title, topics.argmax()))
        f = features[i]
        if usetopics ==True:
            for j,t in enumerate(topics):
                f['topic '+str(j)]= t
        i+=1

    print("Number of instances (in feature vector): "+str(len(features)))
    print("Number of instances (in class vector): "+str(len(classes)))
    min = minclasssize
    featuresn = []
    classesn = []
    titlesn = []
    geoinfon =[]
    if multilabel == False:
        print('Remove classes below minimum frequency : '+str(min))
        counts = Counter(classes)
        print('Class frequency distribution: '+str(counts))
        for i, f in enumerate(features):
                if counts[classes[i]] >=min:
                    classesn.append(classes[i])
                    featuresn.append(features[i])
                    titlesn.append(titles[i])
                    geoinfon.append(geoinfo[i])
    else:
        counts = Counter([classe for sublist in classes for classe in sublist])
        print('Class frequency distribution: '+str(counts))
        classesn = classes
        featuresn = features
        titlesn = titles
        geoinfon = geoinfo


    #print(features)
    #print(classes)
    return (titlesn, classesn,featuresn, geoinfon)


def trainLLDA(jsonfile, textkey, textkey2='gwebtext', language='dutch', usetopics=True, usetypes=True,  actlevel = True, minclasssize = 0):
    """ Method takes the enriched json file (training data), and builds an LDA topic model.
     It trains an LDA topic model on the webtexts, puts everything together in feature vectors and returns this together with the classes as two simple arrays
    Usetypes = True puts also OSMtags and GooglePlace tags into the feature vector, in addition to topics.
    actlevel = True restricts classes to the activity level (no referent classes).
    Minclasssize filters out too small classes."""
    texts = [] #array that holds the LDA text documents
    titles = [] #array that holds the titles of documents (in this case place names)
    classes = [] #array that holds the goal classes
    features = [] #array the holds the feature vectors
    geoinfo = [] #stuf needed to map results

    #testclasses = ['ulo:Eating|ulo:Food']
    with open(jsonfile) as json_data:
        d = json.load(json_data)
        print('Size of the json file: '+str(len(d)))


        #first determine the class frequencies of all classes occurring
        classbag = []
        for k,v in d.items():
            for c in v['class']:
                if actlevel:
                    cl = c.split('|')[0]
                else:
                    cl = c
                classbag.append(cl)
        clfreq = Counter(classbag)
        print(clfreq)

        listofosmids = []
        #print(d)
        for k,v in d.items():
          #Collect features for each osm id. Take only a single goal class fo reach osm id
          if not ( v['osmid'] in listofosmids):
            gtext = ''
            wtext = ''
            if textkey2 in v.keys():
                gtext =v[textkey2]
            if textkey in v.keys():# and 'googletype' in (d[k]).keys():
                wtext =v[textkey]
            if 'reviewtext' in v.keys():
                rtext =v['reviewtext']
            text = (wtext if wtext !='' else ( gtext if gtext != '' else ''))
            if text != '':
                listofosmids.append(v['osmid'])
                texts.append(text)
                titles.append(v['name'])
                dd = {'osmid':k,'name':v['name']}
                if 'lat' in v.keys():
                    dd['lat']=v['lat']
                    dd['lon']=v['lon']
                geoinfo.append(dd)

                #select the class that occurs most frequently over all places as the class of an osm id
                #classize = 0
                cl = []
                #print(v['class'])
                for c in v['class']:
                    if actlevel:
                        x = c.split('|')[0]
                    else:
                        x = c
                    cl.append(x)
                    #if clfreq[x]>classize:
                        #cl = x
                        #classize =clfreq[x]

                classes.append(set(cl)) # remove duplicates if getting activities only
                dic = {}
                #Add the place tags from OSM or GooglePlaces
                if usetypes == True:
                    if 'googletype' in v.keys():
                        dic['googletype'] =v['googletype']
                    #dic['osmtype'] =v['osmtype']
                    for typekey in keysofinterest:
                        if typekey in v.keys():
                            dic[typekey] = v[typekey]
                        else:
                            dic[typekey] = 'No'
                features.append(dic)

    json_data.close

    # This is where the texts get turned into a gensim corpus
    stoplist = stopwords.words(language)
    texts_matrix = [[word for word in text.lower().split() if word not in stoplist] for text in texts]
    dictionary = corpora.Dictionary(texts_matrix)
    #print(dictionary)
    corpus = [dictionary.doc2bow(text) for text in texts_matrix]
    #print(corpus)

    #Converts the class labels to a binary vector
    mlb = MultiLabelBinarizer()
    y_train = mlb.fit_transform(classes)

    # This computes the Labeled LDA model
    model = LLDAClassifier(alpha = 0.5/y_train.shape[1], maxiter=600)
    model.fit(corpus, y_train)

    topics_words = np.loadtxt(model.tmp + "/fit.n_wz").T

    list(mlb.classes_)
    for i in range(0, len(mlb.classes_)):
        cl = mlb.classes_[i]
        print(cl)
        print("---------------")
        s = topics_words[i]
        top_words_idx = sorted(range(len(s)), key=lambda k: s[k])[::-1]
        # print the top 20 words for this topic
        for j in range(0, 20):
            print(dictionary[top_words_idx[j]])
        print("===============")


#Takes an array of label arrays and turns it into an indicator matrix for multilabel classifiers
#test = [['2', '3', '4'], ['2'], ['0', '1', '3'], ['0', '1', '2', '3', '4'], ['0', '1', '2']]
#ToIndicatorMatrix(test)
def ToIndicatorMatrix(arrayofarray):
    from sklearn.preprocessing import MultiLabelBinarizer
    from sklearn import preprocessing
    preprocessing.LabelEncoder()
    le = preprocessing.LabelEncoder()
    labels = list(set([classe for sublist in arrayofarray for classe in sublist]))
    le.fit(labels)
    yp=[le.transform(a) for a in arrayofarray]
    #le.fit(["paris", "paris", "tokyo", "amsterdam"])
    #le.transform(["tokyo", "tokyo", "paris"])
    #list(le.inverse_transform([2, 2, 1]))
    #y = [[2, 3, 4], [2], [0, 1, 3], [0, 1, 2, 3, 4], [0, 1, 2]]
    Y = MultiLabelBinarizer().fit_transform(yp)
    np.set_printoptions(threshold=np.inf)
    #print(Y)
    return Y

def myCVAScore(classifier,X,y, n_splits):
    #CMy validation function
        from sklearn.model_selection import KFold

        accuracylist=[]
        precisionlist=[]
        recalllist=[]
        f1list = []
        coverageerrorlist = []
        hamminglosslist = []
        jaccardlist = []

        # remember to set n_splits and shuffle!
        kf = KFold(n_splits=n_splits, random_state=None, shuffle=False)

        for train_index, test_index in kf.split(X, y):
            # assuming classifier object exists
            X_train = X[train_index,:]
            y_train = y[train_index,:]

            X_test = X[test_index,:]
            y_test = y[test_index,:]

            # learn the classifier
            classifier.fit(X_train, y_train)

            # predict labels for test data
            predictions = classifier.predict(X_test)
            (precision, recall, f1, support) = precision_recall_fscore_support(y_test,predictions, average='weighted')
            accuracylist.append(accuracy_score(y_test,predictions))
            precisionlist.append(precision)
            recalllist.append(recall)
            f1list.append(f1)
            coverageerrorlist.append(coverage_error(y_test,predictions.toarray()))
            hamminglosslist.append(hamming_loss(y_test,predictions))
            jaccardlist.append(jaccard_similarity_score(y_test,predictions))


        return (np.asarray(accuracylist).mean(),np.asarray(precisionlist).mean(), np.asarray(recalllist).mean(),np.asarray(f1list).mean(), np.asarray(coverageerrorlist).mean(), np.asarray(hamminglosslist).mean(), np.asarray(jaccardlist).mean())


def classify(topicmodel, plotconfusionmatrix=False, multilabel =False):
    """ Method takes feature vectors (including topic model) and class labels as arrays, and trains and tests a number of classifiers on them. Outputs classifier scores and confusion matrices."""

    names = [#"Dummy",
    "Logistic Regression","Nearest Neighbors", "Linear SVM", "RBF SVM", "Gaussian Process",
             "Decision Tree", "Random Forest", "Neural Net", "AdaBoost",
             "Naive Bayes"]

    classifiers = [
        #DummyClassifier(strategy='most_frequent',random_state=10),
        LogisticRegression(C=1e5, multi_class="ovr"),
        KNeighborsClassifier(5),
        SVC(kernel="linear", C=0.025),
        SVC(kernel='rbf',gamma=2, C=1),
        GaussianProcessClassifier(1.0 * RBF(1.0), warm_start=True),
        DecisionTreeClassifier(max_depth=5),
        RandomForestClassifier(max_depth=5, n_estimators=10, max_features=1),
        MLPClassifier(alpha=1),
        AdaBoostClassifier(),
        GaussianNB()]

    multinames = ["Logistic Regression", 'MLkNN', 'Decision Tree', 'Extra Tree', 'KNN', 'Neural Net', 'Random Forest', 'Naive Bayes', "RBF SVM","Linear SVM"
    ]
    multiclassifiers = [
        LabelPowerset(LogisticRegression(C=1e5)),
        MLkNN(k=5, s=1.0, ignore_first_neighbours=0),
        LabelPowerset(DecisionTreeClassifier(max_depth=5)),
        LabelPowerset(ExtraTreeClassifier(max_depth=5)),
        LabelPowerset(KNeighborsClassifier(5)),
        LabelPowerset(MLPClassifier(alpha=1)),
        LabelPowerset(RandomForestClassifier(max_depth=5, n_estimators=10, max_features=1)),
        LabelPowerset(GaussianNB()),
        LabelPowerset(SVC(kernel='rbf',gamma=2, C=1)),
        LabelPowerset(SVC(kernel="linear", C=0.025)),

        #RidgeClassifierCV()
        #GaussianProcessClassifier(1.0 * RBF(1.0), warm_start=True, multi_class= "one_vs_rest")
    ]

    measurements = topicmodel[2]
    vec = DictVectorizer()
    X = vec.fit_transform(measurements).toarray()
    print(vec.get_feature_names())
    #print(X)
    classlabels = topicmodel[1]
    Y = (classlabels if multilabel == False else ToIndicatorMatrix(classlabels))
    #print(X)
    #print(y)

   # X_train, X_test, y_train, y_test = \
   #     train_test_split(X, y, test_size=.2, random_state=42)
    classes = (list(set(classlabels)) if multilabel == False else list(set([classe for sublist in classlabels for classe in sublist])))

    #Number of cross validations
    cvn = 5
    print(('\n Start multi-label classification!' if multilabel else 'Start single-label classification!'))
    print('Labels (classes):')
    print(classes)

    #see https://www.analyticsvidhya.com/blog/2017/08/introduction-to-multi-label-classification/
    #http://scikit.ml/api/index.html
    print('\n Results of the model evaluation: \n')

    scores = ['accuracy', 'precision_weighted', 'recall_weighted', 'f1_weighted' ]

    #Naive model (majority vote)
    clf = DummyClassifier(strategy='most_frequent',random_state=10)
    if multilabel:
        clf = LabelPowerset(clf)
    dummyscores = cross_val_score(clf,X,Y,cv=cvn, scoring=scores[0])
    dummyprescores = cross_val_score(clf,X,Y,cv=cvn, scoring=scores[1])
    dummyrescores = cross_val_score(clf,X,Y,cv=cvn, scoring=scores[2])
    dummyfescores = cross_val_score(clf,X,Y,cv=cvn, scoring=scores[3])
    print("\n {}-CV naive classifier (most frequent class): {}: {} (+/- {}), {}: {}, {}: {}, {}: {}".format(cvn,scores[0],dummyscores.mean(),dummyscores.std(),scores[1],dummyprescores.mean(),scores[2],dummyrescores.mean(), scores[3],dummyfescores.mean()))
    y_pred = clf.fit(X, Y).predict(X)
    if multilabel == False:
        print("Fitting on entire dataset (no CV):")
        cnf_matrix = metrics.confusion_matrix(Y, y_pred,labels=classes)
        print(cnf_matrix)
        print(metrics.classification_report(Y, y_pred,labels=classes))
    else:
        myscores = myCVAScore(clf,X,Y,cvn)
        print ("\n {}-CV naive classifier (my own) {}: {}, {}: {}, {}: {}, {}: {}, {}: {}, {}: {}, {}: {}".format(cvn,scores[0],myscores[0],scores[1],myscores[1],scores[2],myscores[2], scores[3],myscores[3],'coverage', myscores[4], 'hamming loss', myscores[5], 'jaccard', myscores[6]))
        print("Fitting on entire dataset (no CV):")
        print('subset accuracy: {}'.format(accuracy_score(y_pred,Y)))




     # iterate over classifiers
    classifiers = (multiclassifiers if multilabel else classifiers)
    names = (multinames if multilabel else names)
    for name, clf in zip(names, classifiers):
        #standard scores given by sklearn
        accscores = cross_val_score(clf,X,Y,cv=cvn, scoring=scores[0])
        pscores = cross_val_score(clf,X,Y,cv=cvn, scoring=scores[1])
        rscores = cross_val_score(clf,X,Y,cv=cvn, scoring=scores[2])
        fscores = cross_val_score(clf,X,Y,cv=cvn, scoring=scores[3])
        print("\n {}-CV  {}: {}: {} (+/- {}), {}: {}, {}: {}, {}: {}".format(cvn,name,scores[0],accscores.mean(), accscores.std(),scores[1],pscores.mean(), scores[2],rscores.mean(), scores[3],fscores.mean()))

        clffit = clf.fit(X, Y)
        y_pred = clffit.predict(X)
        if multilabel==False:
            print("Fitting on entire dataset (no CV):")
            cnf_matrix = metrics.confusion_matrix(Y, y_pred,labels=classes)
            print(cnf_matrix)
            print(metrics.classification_report(Y, y_pred,labels=classes))
        else:
            #my own scores for multilabel classification
            myscores = myCVAScore(clf,X,Y,cvn)
            print ("\n {}-CV {} (my own): {}: {}, {}: {}, {}: {}, {}: {}, {}: {}, {}: {}, {}: {}".format(cvn,name,scores[0],myscores[0],scores[1],myscores[1],scores[2],myscores[2], scores[3],myscores[3],'coverage', myscores[4], 'hamming loss', myscores[5], 'jaccard', myscores[6]))
            print("Fitting on entire dataset (no CV):")
            print(' subset accuracy: {}'.format(accuracy_score(y_pred,Y)))



        #print decision tree
        from sklearn import tree
        if name == "Decision Tree" and multilabel == False:
            tree.export_graphviz(clffit, out_file='tree.dot', class_names=sorted(classes), feature_names=vec.get_feature_names())



        # Plot non-normalized confusion matrix
        #plt.figure()
        np.set_printoptions(precision=2)
        if plotconfusionmatrix:
            plot_confusion_matrix(cnf_matrix, classes=classes, title='Confusion matrix for '+name)

#generates a plotted confusion matrix
def plot_confusion_matrix(cm, classes,
                          normalize=False,
                          title='Confusion matrix',
                          cmap=plt.cm.Blues):
    """
    This function prints and plots the confusion matrix.
    Normalization can be applied by setting `normalize=True`.
    """

    plt.imshow(cm, interpolation='nearest', cmap=cmap)
    plt.title(title)
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=45)
    plt.yticks(tick_marks, classes)

    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        print("Normalized confusion matrix")
    else:
        print('Confusion matrix, without normalization')

    print(cm)

    thresh = cm.max() / 2.
    for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
        plt.text(j, i, cm[i, j],
                 horizontalalignment="center",
                 color="white" if cm[i, j] > thresh else "black")

    plt.tight_layout()
    plt.ylabel('True label')
    plt.xlabel('Predicted label')
    plt.show()

#This method exports a shape file to map the result
def exportSHP(topicmodel, shpfilename):
    from types import *
    from fiona.crs import from_epsg

    geoinfo = topicmodel[3]
    features = topicmodel[2]
    classes = topicmodel[1]
    # Here's an example Shapely geometry

    # Define a polygon feature geometry with one attribute
    properties = {'id': 'str', 'name': 'str'}
##    for k,v in features[0].items():
##        if type(v) is np.float64:
##            fieldname = k[:10].replace(" ", "_")
##            properties[fieldname]='float'
##        elif type(v) is float:
##            fieldname = k[:10].replace(" ", "_")
##            properties[fieldname]='float'
##        elif type(v) is int:
##            fieldname = k[:10].replace(" ", "_")
##            properties[fieldname]='int'
##        elif type(v) is str:
##            fieldname = k[:10].replace(" ", "_")
##            properties[fieldname]='str'

    classlabels = {l for p in classes for l in p}
    print(classlabels)
    for label in classlabels:
            fieldname = label[:10].replace(":", "_")#.replace(':', "_")
            properties[fieldname]='int'

    schema = {
        'geometry': 'Point',
        'properties': properties
    }

    with fiona.open(shpfilename, 'w', crs=from_epsg(4326),driver= 'ESRI Shapefile', schema=schema) as c:
    ## If there are multiple geometries, put the "for" loop here
        for i,g in enumerate(geoinfo):
            if 'lon' in g.keys() and 'lat' in g.keys() and float(g['lon'])<40.0:
                point = Point(float(g['lon']), float(g['lat']))
                attributes ={'id': g['osmid'], 'name':g['name']}
##                for k,v in features[i].items():
##                    fieldname = k[:10].replace(" ", "_")
##                    attributes[fieldname]=v
                for label in classlabels:
                    fieldname = label[:10].replace(":", "_")#.replace(':', "_")
                    if label in classes[i]:
                        attributes[fieldname]=1
                    else:
                        attributes[fieldname]=0

                c.write({
                'geometry': mapping(point),
                'properties': attributes
                })
                #jj

        c.close


    # Write a new Shapefile


#This method writes data missing in trainingdata from trainingdataadd, thus unifies web scraping results.
def unifyWebInfo(trainingdata, trainingdataadd):
    newtrainingdata = {}
    out = trainingdata.split('.')[0]+'_u.json'
    with open(trainingdata) as training_data:
        trainingdata = json.load(training_data)
        with open(trainingdataadd) as training_dataadd:
            trainingdataadd = json.load(training_dataadd)
            counttrain = 0
            countadd = 0
            for k,v in trainingdata.items():
                counttrain +=1
                newv = v.copy()
                tags = ['website', 'webtitle', 'webtext','name', 'reviewtext', 'googletype', 'GoogeId', 'lat', 'lon', 'shop', 'amenity', 'leisure', 'tourism', 'historic', 'man_made', 'tower', 'cuisine', 'clothes', 'tower', 'beer', 'highway', 'surface', 'place', 'building' ]
                vv = (trainingdataadd[k] if k in trainingdataadd.keys() else None)
                if vv is not None:
                    for t in tags:
                        if t not in v.keys() and t in vv.keys():
                            if k.split(':')[0] != 'osmw' or t not in ['lat','lon']:
                                countadd +=1
                                newv[t] = vv[t]
                newtrainingdata[k]=newv
    training_data.close()
    print('In '+str(counttrain)+' entities, in '+ str(countadd) +' cases something was added!')

    with open(out, 'w') as fp:
        json.dump(newtrainingdata, fp)






if __name__ == '__main__':
    #constructTrainingData('training.csv', write=False)
    #unifyWebInfo('training_train.json','oldfiles/training_train_best.json')

    topicmodel = trainLDA('training_train_u.json', 'webtext', language='dutch', usetypes=True, actlevel=True, multilabel=True)
    #classify(topicmodel, multilabel=False)
    #topicmodel = trainLDA('training_train_u.json', 'reviewtext', language='english', usetypes=True, actlevel=True, multilabel=True)
    #classify(topicmodel, multilabel=True)
    #topicmodel = trainLDA('training_train_u.json', 'reviewtext', language='english', usetypes=True, actlevel=True, minclasssize=0, multilabel=False)
    #classify(topicmodel, multilabel=False)
    #topicmodel = trainLDA('training_train_u.json', 'reviewtext', language='english', usetypes=True, actlevel=True, multilabel=True)
    #classify(topicmodel, multilabel=True)

    #topicmodel_llda = trainLLDA('training_train_u.json', 'webtext', language='dutch', usetypes=False, actlevel=True, minclasssize=0)



    exportSHP(topicmodel,'placetopics.shp')






