# -*- coding: utf-8 -*-
"""
-------------------------------------------------
   File Name：     main.py
   Description :
   Author :       Liangs
   date：          2019/7/28
-------------------------------------------------
   Change Activity:
                   2019/10/29:
-------------------------------------------------
"""
import os
import random
import torch
import numpy as np
import pathlib
import shutil
from datetime import datetime
from utils.arguments import parse_args
from models.biaffine_trainer import BERTologyBiaffineTrainer
from models.biaffine_model import BiaffineDependencyModel
from utils.input_utils.bertology.bert_input_utils import load_bertology_input
from utils.input_utils.graph_vocab import GraphVocab
from utils.seed import set_seed
from utils.timer import Timer
from utils.logger import init_logger, get_logger


def load_trainer(args):
    if args.run_mode == 'train':
        # 默认train模式下是基于原始BERT预训练模型的参数开始的
        model = BiaffineDependencyModel.from_pretrained(args, initialize_from_bertology=True)
    else:
        model = BiaffineDependencyModel.from_pretrained(args, initialize_from_bertology=False)
    model.to(args.device)

    # multi-gpu training (should be after apex fp16 initialization)
    if args.n_gpu > 1:
        model = torch.nn.DataParallel(model)
        print(f'Parallel Running, GPU num : {args.n_gpu}')
        args.parallel_train = True
    else:
        args.parallel_train = False
    if args.encoder_type == 'bertology':
        trainer = BERTologyBiaffineTrainer(args, model)
    else:
        raise ValueError('Encoder Type not supported temporarily')
    return trainer


def config_for_multi_gpu(args):
    args.device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    if args.cuda:
        args.n_gpu = torch.cuda.device_count()
    else:
        args.n_gpu = 0
    args.train_batch_size = args.per_gpu_train_batch_size * max(1, args.n_gpu)
    args.eval_batch_size = args.per_gpu_eval_batch_size * max(1, args.n_gpu)


def make_output_dir(args):
    assert args.run_mode == 'train', '仅在train模式下保存各种输出文件'
    output_dir = pathlib.Path(args.output_dir)
    assert output_dir.is_dir()
    time_str = datetime.now().strftime('_%Y-%m-%d-%H-%M-%S')
    output_dir = output_dir / (pathlib.Path(args.config_file).stem + time_str)
    if output_dir.exists():
        raise RuntimeError(f'{output_dir} exists! (maybe file or dir)')
    else:
        output_dir.mkdir()
        # 复制对应的配置文件到保存的文件夹下，保持配置和输出结果的一致
        shutil.copyfile(args.config_file, str(output_dir / pathlib.Path(args.config_file).name))
        # 复制graphVocab到输出文件下：
        shutil.copyfile(args.graph_vocab_file, str(output_dir / pathlib.Path(args.graph_vocab_file).name))
        (output_dir / 'model').mkdir()
        args.output_dir = str(output_dir)
        args.dev_output_path = str(output_dir / 'dev_output_conllu.txt')
        args.dev_result_path = str(output_dir / 'dev_best_metrics.txt')
        args.test_output_path = str(output_dir / 'test_output_conllu.txt')
        args.test_result_path = str(output_dir / 'test_metrics.txt')
        args.output_model_dir = str(output_dir / 'model')
        args.summary_dir = str(output_dir / 'summary')
        init_logger(args.log_name, str(output_dir / 'parser.log'))


def train(args):
    assert args.run_mode == 'train'
    # 创建输出文件夹，保存运行结果，配置文件，模型参数
    make_output_dir(args)

    with Timer('load input'):
        # 目前仅仅支持BERTology形式的输入
        train_data_loader, train_conllu, dev_data_loader, dev_conllu = load_bertology_input(args)

    print(f'train batch size: {args.train_batch_size}')
    print(f'train data batch num: {len(train_data_loader)}')
    # 每个epoch做两次dev：
    args.eval_interval = len(train_data_loader) // 2
    print(f'eval interval: {args.eval_interval}')
    # 注意该参数影响学习率warm up
    args.max_train_steps = len(train_data_loader) * args.max_train_epochs
    print(f'max steps: {args.max_train_steps}')
    # 如果6个epoch之后仍然不能提升，就停止
    if args.early_stop:
        args.early_stop_steps = len(train_data_loader) * args.early_stop_epochs
        print(f'early stop steps: {args.early_stop_steps}\n')
    else:
        print(f'do not use early stop, training will last {args.max_train_epochs} epochs')
    with Timer('load trainer'):
        trainer = load_trainer(args)
    with Timer('Train'):
        trainer.train(train_data_loader, dev_data_loader, dev_conllu)
    print('train DONE')


def dev(args):
    # args = trainer.args
    assert args.run_mode == 'dev'
    dev_data_loader, dev_conllu = load_bertology_input(args)
    with Timer('load trainer'):
        trainer = load_trainer(args)
    with Timer('dev'):
        dev_UAS, dev_LAS = trainer.dev(dev_data_loader, dev_conllu,
                                       input_conllu_path=args.input_conllu_path,
                                       output_conllu_path=args.output_conllu_path)
    print(f'DEV output file saved in {args.output_conllu_path}')
    print(f'DEV metrics:\nUAS:{dev_UAS}\nLAS:{dev_LAS}')


def inference(args):
    # args = trainer.args
    assert args.run_mode == 'inference'
    inference_data_loader, inference_conllu = load_bertology_input(args)
    with Timer('load trainer'):
        trainer = load_trainer(args)
    with Timer('inference'):
        trainer.inference(inference_data_loader, inference_conllu, output_conllu_path=args.output_conllu_path)
    print(f'INFERENCE output file saved in {args.output_conllu_path}')


def main():
    with Timer('parse args'):
        args = parse_args()
    # 添加多卡运行下的配置参数
    # BERT训练须在多卡下运行，单卡非常慢
    config_for_multi_gpu(args)
    # set_seed 必须在设置n_gpu之后
    set_seed(args)

    if args.run_mode == 'train':
        train(args)
    elif args.run_mode == 'dev':
        dev(args)
    elif args.run_mode == 'inference':
        inference(args)


if __name__ == '__main__':
    main()
