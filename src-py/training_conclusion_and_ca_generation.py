import transformers
import datasets

import torch
import json
import argparse
import nltk
import numpy as np
import pandas as pd

from utils import *


from pathlib import Path
from datasets import load_dataset, load_metric, Dataset

from transformers import AutoModelForSeq2SeqLM, DataCollatorForSeq2Seq, Seq2SeqTrainingArguments, Seq2SeqTrainer
from transformers import BartTokenizer, BartForConditionalGeneration


max_input_length = 512
max_target_length = 200



tokenizer = BartTokenizer.from_pretrained('facebook/bart-base')
model = BartForConditionalGeneration.from_pretrained('facebook/bart-base')

#Add special tokens
special_tokens_dict = {'additional_special_tokens': ['<conclusion>', '</conclusion>','<premises>', '</premises>', '<counter>']}
num_added_toks = tokenizer.add_special_tokens(special_tokens_dict)
model.resize_token_embeddings(len(tokenizer))


def train_model(train_ds, valid_ds, output_dir, training_batch_size=2, valid_batch_size=4, epochs=3):

    args = Seq2SeqTrainingArguments(
        output_dir,
        evaluation_strategy = "steps",
        learning_rate=2e-5,
        per_device_train_batch_size=training_batch_size,
        per_device_eval_batch_size=valid_batch_size,
        weight_decay=0.01,
        save_total_limit=5,
        num_train_epochs=epochs,
        load_best_model_at_end=True,
        metric_for_best_model='bert-fscore',
        predict_with_generate=True
    )


    data_collator = DataCollatorForSeq2Seq(tokenizer, model=model)

    trainer = Seq2SeqTrainer(
        model,
        args,
        train_dataset=train_ds,
        eval_dataset=valid_ds,
        data_collator=data_collator,
        tokenizer=tokenizer,
        compute_metrics=lambda x : compute_metrics(x, tokenizer)
    )

    trainer.train()
    trainer.save_model()

#CUDA_VISIABLE_DEVICES=0 python training_conclusion_and_ca_generation.py --train_data ../data/train_conclusion_comp_remove_75sem_perc.pkl --valid_data ../data/valid_conclusion_comp_remove_75sem_perc.pkl --output_dir ../data/output/known-conclusion-bart-model --downsample_valid=0.1 --train_bs=16 --valid_bs=16 --train_epochs=3
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Finetune a transformers model on a argument gen task")
    
    parser.add_argument(
        '--masked_conclusion', action="store_true"
    )
    
    parser.add_argument(
        '--conclusion_and_counter_generation', action="store_true"
    )
    
    parser.add_argument(
        '--train_data', type=str
    )
    
    parser.add_argument(
        '--valid_data', type=str
    )

    parser.add_argument(
        '--output_dir', type=str
    )

    parser.add_argument(
        '--downsample_training', type=float, default=1
    )
    
    parser.add_argument(
        '--downsample_valid', type=float, default=1
    )

    parser.add_argument(
        '--premises_clm', type=str, default='masked_premises'
    )
    parser.add_argument(
        '--conclusion_clm', type=str, default='title'
    )
    parser.add_argument(
        '--counter_clm', type=str, default='counter'
    )
    parser.add_argument('--max_source_length', type=int, default=512)
    parser.add_argument('--max_target_length', type=int, default=200)
    parser.add_argument('--train_bs', type=int, default=32)
    parser.add_argument('--valid_bs', type=int, default=32)
    parser.add_argument('--train_epochs', type=int, default=6)
    
    args = parser.parse_args()

    train_ds = Dataset.from_pandas(pd.read_pickle(args.train_data))
    valid_ds = Dataset.from_pandas(pd.read_pickle(args.valid_data))


    if args.downsample_training < 1:
        #downsample the training dataset
        tmp_ds = train_ds.train_test_split(args.downsample_training)
        train_ds = tmp_ds['test']


    if args.downsample_valid < 1:
        #downsample the valid dataset
        tmp_ds = valid_ds.train_test_split(args.downsample_valid)
        valid_ds = tmp_ds['test']


    if args.masked_conclusion:
        training_enc_ds = train_ds.map(lambda x :preprocess_function(x, tokenizer, args.premises_clm, args.counter_clm, max_target_length=args.max_target_length, max_input_length=args.max_source_length), batched=True)
        valid_enc_ds = valid_ds.map(lambda x :preprocess_function(x, tokenizer, args.premises_clm, args.counter_clm, max_target_length=args.max_target_length, max_input_length=args.max_source_length), batched=True)
        
    elif args.conclusion_and_counter_generation:
        training_enc_ds = train_ds.map(lambda x :preprocess_function(x, tokenizer, args.premises_clm, args.counter_clm, conclusion_clm=args.conclusion_clm, conclusion_in_output=True, max_target_length=args.max_target_length, max_input_length=args.max_source_length), batched=True)
        valid_enc_ds = valid_ds.map(lambda x :preprocess_function(x, tokenizer, args.premises_clm, args.counter_clm, conclusion_clm=args.conclusion_clm, conclusion_in_output=True, max_target_length=args.max_target_length, max_input_length=args.max_source_length), batched=True)
    else:
        training_enc_ds = train_ds.map(lambda x :preprocess_function(x, tokenizer, args.premises_clm, args.counter_clm, conclusion_clm=args.conclusion_clm, max_target_length=args.max_target_length, max_input_length=args.max_source_length), batched=True)
        valid_enc_ds = valid_ds.map(lambda x :preprocess_function(x, tokenizer, args.premises_clm, args.counter_clm, conclusion_clm=args.conclusion_clm, max_target_length=args.max_target_length, max_input_length=args.max_source_length), batched=True)


    train_model(training_enc_ds, valid_enc_ds, args.output_dir, args.train_bs, args.valid_bs, args.train_epochs)