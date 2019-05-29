import sys
import pandas as pd
import numpy as np
import pickle # enables saving data and models locally

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2' # ignore tensorflow warnings

import tensorflow_hub as hub
import tensorflow as tf

def elmo_vectors(arr, sess, model, current_batch = 0, num_batches = 0, data_rows = 0):
    # initialise ELMo model
    embeddings = model(arr, signature="default", as_dict=True)["elmo"]
    
    # display progress
    if num_batches and current_batch and data_rows:
        status_text = f"Extracting ELMo features from the {data_rows} rows... "
        status_perc = round(current_batch / num_batches * 100, 2)
        print(f"{status_text} {status_perc}% completed.", end = "\r")

    # return average of ELMo features
    return sess.run(tf.reduce_mean(embeddings, 1))

def extract(arr, batch_size = 50):
    # load the ELMo model
    model = hub.Module("elmo", trainable = True)

    # get the amount of rows in the array
    data_rows = len(arr)
    
    status_text = f"Extracting ELMo features from the {data_rows} rows... "
    print(status_text + " 0.0% completed.", end = "\r")

    # set up batches
    batches = np.asarray([arr[i:i+batch_size] for i in 
                np.arange(0, data_rows, batch_size)])
    num_batches = len(batches)

    # build ELMo data
    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())
        sess.run(tf.tables_initializer())
        elmo_batches = np.asarray([
            elmo_vectors(
                arr = batch, 
                sess = sess, 
                model = model, 
                current_batch = current_batch, 
                num_batches = num_batches,
                data_rows = data_rows
            )
            for current_batch, batch in enumerate(batches)])

    return np.concatenate(elmo_batches, axis = 0)