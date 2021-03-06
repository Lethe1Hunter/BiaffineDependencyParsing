# -*- coding: utf-8 -*-
# Created by li huayong on 2019/10/7
import os
import pathlib

import torch
import torch.nn as nn

from utils.input_utils.bertology.bert_input_utils import load_bert_tokenizer, load_and_cache_examples, get_data_loader
from utils.input_utils.graph_vocab import GraphVocab
from modules.bertology_encoder import BERTologyEncoder
from modules.biaffine import DeepBiaffineScorer, DirectBiaffineScorer
from models.base_model import BaseModel


class BiaffineDependencyModel(BaseModel):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.graph_vocab = GraphVocab(args.graph_vocab_file)
        if args.encoder_type == 'bertology':
            # args.encoder_type 控制用什么类型的encoder（EBRTology/Transformer等等）
            # args.bertology_type 控制具体是什么类型的BERT（bert/xlnert/roberta等等）
            self.encoder = BERTologyEncoder(no_cuda=not args.cuda,
                                            bertology=args.bertology_type,
                                            bertology_path=args.saved_model_path,
                                            bertology_word_select_mode=args.bertology_word_select,
                                            bertology_output_mode=args.bertology_output_mode,
                                            max_seq_len=args.max_seq_len,
                                            bertology_after=args.bertology_after,
                                            after_layers=args.after_layers,
                                            after_dropout=args.after_dropout)
        elif args.encoder_type in ['lstm', 'gru']:
            self.encoder = None  # Do NOT support now #todo
        elif args.encoder_type == 'transformer':
            self.encoder = None  # Do NOT support now #todo
        if args.direct_biaffine:
            self.unlabeled_biaffine = DirectBiaffineScorer(args.encoder_output_dim,
                                                           args.encoder_output_dim,
                                                           1, pairwise=True)
            self.labeled_biaffine = DirectBiaffineScorer(args.encoder_output_dim,
                                                         args.encoder_output_dim,
                                                         len(self.graph_vocab.get_labels()),
                                                         pairwise=True)
        else:
            self.unlabeled_biaffine = DeepBiaffineScorer(args.encoder_output_dim,
                                                         args.encoder_output_dim,
                                                         args.biaffine_hidden_dim,
                                                         1, pairwise=True,
                                                         dropout=args.biaffine_dropout)
            self.labeled_biaffine = DeepBiaffineScorer(args.encoder_output_dim,
                                                       args.encoder_output_dim,
                                                       args.biaffine_hidden_dim,
                                                       len(self.graph_vocab.get_labels()),
                                                       pairwise=True,
                                                       dropout=args.biaffine_dropout)
        # self.dropout = nn.Dropout(args.dropout)
        if args.learned_loss_ratio:
            self.label_loss_ratio = nn.Parameter(torch.Tensor([0.5]))
        else:
            self.label_loss_ratio = args.label_loss_ratio

    def forward(self, inputs):
        assert isinstance(inputs, dict)
        encoder_output = self.encoder(**inputs)
        unlabeled_scores = self.unlabeled_biaffine(encoder_output, encoder_output).squeeze(3)
        labeled_scores = self.labeled_biaffine(encoder_output, encoder_output)
        return unlabeled_scores, labeled_scores


if __name__ == '__main__':
    class Args():
        def __init__(self):
            self.bert_path = '/home/liangs/disk/data/bertology-base-chinese'
            self.data_dir = '../dataset'
            self.train_file = 'test.conllu'
            self.max_seq_length = 10
            self.encoder_type = 'bertology'
            self.root_representation = 'unused'
            self.graph_vocab_file = '../dataset/graph_vocab.txt'
            self.cuda = False
            self.bert_chinese_word_select = 's+e'
            self.bert_output_mode = 'last_four_sum'

            # for Biaffine
            self.biaffine_hidden_dim = 300
            self.biaffine_dropout = 0.1

            # for loss:
            self.learned_loss_ratio = True,
            self.label_loss_ratio = 0.5


    args = Args()

    if args.encoder_type == 'bertology':
        args.encoder_output_dim = 768

    tokenizer = load_bert_tokenizer('/home/liangs/disk/data/bertology-base-chinese', 'bertology')
    vocab = GraphVocab('../dataset/graph_vocab.txt')
    dataset, CoNLLU_file = load_and_cache_examples(args, vocab, tokenizer)
    data_loader = get_data_loader(dataset, batch_size=2, evaluation=True)
    # bertology = BERTTypeEncoder(no_cuda=True, bert_path=args.bert_path)
    model = BiaffineDependencyModel(args)
    print(model)
    for batch in data_loader:
        inputs = {
            'input_ids': batch[0],
            'attention_mask': batch[1],
            'token_type_ids': batch[2] if args.encoder_type in ['bertology', 'xlnet'] else None,
            'start_pos': batch[3],
            'end_pos': batch[4],
        }
        # print(inputs)
        # print(inputs['start_pos'])
        output = model(inputs)
        print(output)
