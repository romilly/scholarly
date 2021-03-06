import torch
import numpy as np
import pandas as pd
from torch.utils import data
from pathlib import Path
from tqdm.auto import tqdm
from utils import get_path

class BatchWrapper:
    ''' Wrap a torchtext data iterator. '''
    def __init__(self, data_iter, vectors: str, cats: list):
        self.data_iter = data_iter
        self.batch_size = data_iter.batch_size
        self.vectors = vectors
        self.cats = cats

    def __iter__(self):
        for batch in self.data_iter:
            x = batch.text
            y = torch.cat([getattr(batch, cat).unsqueeze(1) 
                for cat in self.cats], dim = 1).float()
            yield (x, y)

    def __len__(self):
        return len(self.data_iter)

def preprocess_data(
    tsv_fname: str = 'arxiv_data', 
    txt_fname: str = 'preprocessed_docs.txt', 
    data_dir: str = '.data', 
    batch_size: int = 1000):
    ''' 
    Preprocess text data. This merges titles and abstracts and separates 
    tokens by spaces. It saves this into a text file and also saves a
    dataframe with all the categories. Note that this function uses a 
    constant amount of memory, which is achieved by working in batches 
    and writing directly to the disk.
    
    INPUT
        tsv_fname: str
            The name of the tsv file containing all the categories, 
            without file extension
        txt_fname: str
            The name of the txt file containing the preprocessed texts
        data_dir: str = '.data'
            The data directory
        batch_size: int = 1000
            The amount of rows being preprocessed at a time
    '''
    import spacy

    # Specify the input- and output paths
    cats_in = get_path(data_dir) / (tsv_fname + '.tsv')
    cats_out = get_path(data_dir) / (tsv_fname + '_pp.tsv')
    txt_path = get_path(data_dir) / txt_fname

    # Load the English spaCy model used for tokenisation
    nlp = spacy.load('en')
    tokenizer = nlp.Defaults.create_tokenizer(nlp)
   
    # Load in the dataframe, merge titles and abstracts and batch them
    df = pd.read_csv(cats_in, sep = '\t', usecols = ['title', 'abstract'])
    df.dropna(inplace = True)
    docs = '-TITLE_START- ' + df['title'] + ' -TITLE_END- '\
           '-ABSTRACT_START- ' + df['abstract'] + ' -ABSTRACT_END-'
    del df

    # Tokenisation loop
    with tqdm(desc = 'Preprocessing texts', total = len(docs)) as pbar:
        with open(txt_path, 'w') as f:
            for doc in tokenizer.pipe(docs, batch_size = batch_size):
                f.write(' '.join(tok.text for tok in doc) + '\n')
                pbar.update()

    # Add the preprocessed texts to the dataframe as the first column 
    # and save to disk
    df = pd.read_csv(cats_in, sep = '\t').dropna()
    df.drop(columns = ['title', 'abstract'], inplace = True)
    cats = df.columns.tolist()
    with open(txt_path, 'r') as f:
        df['text'] = f.readlines()
    df = df[['text'] + cats]
    df.to_csv(cats_out, sep = '\t', index = False)

def load_data(tsv_fname: str = 'arxiv_data', data_dir: str = '.data', 
    batch_size: int = 32, split_ratio: float = 0.95,
    random_seed: int = 42, vectors: str = 'fasttext') -> tuple:
    ''' 
    Loads the preprocessed data, tokenises it, builds a vocabulary,
    splits into a training- and validation set, numeralises the texts,
    batches the data into batches of similar text lengths and pads 
    every batch.

    INPUT
        tsv_fname: str = 'arxiv_data'
            The name of the tsv file, without file extension
        data_dir: str = '.data'
            The data directory
        batch_size: int = 32,
            The size of each batch
        split_ratio: float = 0.95
            The proportion of the dataset reserved for training
        vectors: {'fasttext', 'glove'} = 'fasttext'
            The type of word vectors to use. Here the FastText vectors are
            trained on the abstracts and the GloVe vectors are pretrained
            on the 6B corpus
        random_seed: int = 42
            A random seed to ensure that the same training/validation split
            is achieved every time. If set to None then no seed is used.

    OUTPUT
        A triple (train_iter, val_iter, params), with train_iter and val_iter
        being the iterators that iterates over the training- and validation
        samples, respectively, and params is a dictionary with entries:
            vocab_size
                The size of the vocabulary
            emb_dim
                The dimension of the word vectors
            emb_matrix
                The embedding matrix containing the word vectors
    '''
    from torchtext import data, vocab
    from utils import get_cats
    import random

    # Define the two types of fields in the tsv file
    TXT = data.Field()
    CAT = data.Field(sequential = False, use_vocab = False, is_target = True)

    # Set up the columns in the tsv file with their associated fields
    cats = get_cats(data_dir = data_dir)['id']
    fields = [('text', TXT)] + [(cat, CAT) for cat in cats]

    # Load in the dataset and tokenise the texts
    dataset = data.TabularDataset(
        path = get_path(data_dir) / f'{tsv_fname}.tsv',
        format = 'tsv',
        fields = fields,
        skip_header = True
    )

    # Split into a training- and validation set
    if random_seed is None:
        train, val = dataset.split(split_ratio = split_ratio)
    else:
        random.seed(random_seed)
        train, val = dataset.split(
            split_ratio = split_ratio, 
            random_state = random.getstate()
        )

    # Get the word vectors
    vector_cache = get_path(data_dir)
    base_url = 'https://filedn.com/lRBwPhPxgV74tO0rDoe8SpH/scholarly_data/'
    vecs = vocab.Vectors(
        name = vectors, 
        cache = vector_cache, 
        url = base_url + vectors
    )

    # Build the vocabulary of the training set
    TXT.build_vocab(train, vectors = vecs)

    # Numericalise the texts, batch them into batches of similar text
    # lengths and pad the texts in each batch
    train_iter, val_iter = data.BucketIterator.splits(
        datasets = (train, val),
        batch_size = batch_size,
        sort_key = lambda sample: len(sample.text)
    )

    # Wrap the iterators to ensure that we output tensors
    train_dl = BatchWrapper(train_iter, vectors = vectors, cats = cats)
    val_dl = BatchWrapper(val_iter, vectors = vectors, cats = cats)

    del dataset, train, val, train_iter, val_iter
    return train_dl, val_dl, TXT.vocab


if __name__ == '__main__':
    preprocess_data()
