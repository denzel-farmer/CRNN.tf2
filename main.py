import argparse
import time

import numpy as np
import tensorflow as tf

from model import CRNN
from dataset import OCRDataLoader, map_to_chars

parser = argparse.ArgumentParser(description="Process some integers.")
parser.add_argument("-m", "--mode", default="train", required=True, help="train or test.")
parser.add_argument("-p", "--annotation_path", type=str, required=True, help="The path of annnotation file.")
parser.add_argument("--image_height", type=int, default=32, help="Image height(32). If you change this, you should change the structure of CNN.")
parser.add_argument("-w", "--image_width", type=int, default=100, help="Image width(>=16).")
parser.add_argument("-t", "--table_path", type=str, required=True, help="The path of table file.")
parser.add_argument("-b", "--batch_size", type=int, default=32, help="Batch size.")
parser.add_argument("-e", "--epoches", type=int, default=100, help="Num of epoch to train")
parser.add_argument("-r", "--learning_rate", type=float, default=0.0001, help="Learning rate.")
parser.add_argument("--checkpoint_path", type=str, help="The checkpoint path.")
args = parser.parse_args()

with open(args.table_path, "r") as f:
    int_to_char = [char.strip() for char in f]
num_classes = len(int_to_char)
blank_index = num_classes - 1 # Make sure the blank index is what.

@tf.function
def train_one_step(model, X, y, optimizer):
    with tf.GradientTape() as tape:
        y_pred = model(X, training=True)
        loss = tf.nn.ctc_loss(labels=y,
                              logits=tf.transpose(y_pred, perm=[1, 0, 2]),
                              label_length=None,
                              logit_length=[y_pred.shape[1]]*y_pred.shape[0],
                              blank_index=blank_index)
        loss = tf.reduce_mean(loss)
    grads = tape.gradient(loss, model.trainable_variables)
    optimizer.apply_gradients(grads_and_vars=zip(grads, model.trainable_variables))
    return loss

def train(num_classes):
    dataloader = OCRDataLoader(args.annotation_path, 
                               args.image_height, 
                               args.image_width, 
                               table_path=args.table_path,
                               blank_index=blank_index,
                               shuffle=True, 
                               batch_size=args.batch_size)
    model = CRNN(num_classes)
    optimizer = tf.keras.optimizers.Adam(learning_rate=args.learning_rate)

    dirname = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
    checkpoint = tf.train.Checkpoint(model=model)
    manager = tf.train.CheckpointManager(checkpoint, directory="./ckpt/{}".format(dirname), max_to_keep=5)
    summary_writer = tf.summary.create_file_writer("./tensorboard/{}".format(dirname))

    step = 0
    for epoch in range(args.epoches):
        losses = []
        for X, y in dataloader():
            loss = train_one_step(model, X, y, optimizer)
            losses.append(loss.numpy())
            with summary_writer.as_default():
                tf.summary.scalar("loss", loss, step=step)
            step += 1
        print("[{} / {}] Mean loss: {}".format(epoch, args.epoches, np.mean(losses)))
        if epoch % 1 == 0:
            path = manager.save(checkpoint_number=epoch)
            print("model saved to {}".format(path))
        with summary_writer.as_default():
            tf.summary.image("train_image", X, step=step)

def test(num_classes):
    dataloader = OCRDataLoader(args.annotation_path, 
                               args.image_height, 
                               args.image_width, 
                               table_path=args.table_path,
                               blank_index=blank_index,
                               shuffle=True, 
                               batch_size=args.batch_size)
    model = CRNN(num_classes)
    checkpoint = tf.train.Checkpoint(model=model)
    checkpoint.restore(tf.train.latest_checkpoint(args.checkpoint_path))

    for X, y in dataloader():
        start_time = time.perf_counter()
        y_pred = model(X)
        decoded, neg_sum_logits = tf.nn.ctc_greedy_decoder(inputs=tf.transpose(y_pred, perm=[1, 0, 2]),
                                                           sequence_length=[y_pred.shape[1]]*y_pred.shape[0],
                                                           merge_repeated=True)
        decoded = tf.sparse.to_dense(decoded[0], default_value=blank_index).numpy()
        y = tf.sparse.to_dense(y, default_value=blank_index).numpy()
        print("[timing] {} y: {}, decoded: {}".format(time.perf_counter()-start_time, 
                                                      map_to_chars(y, int_to_char, blank_index=blank_index), 
                                                      map_to_chars(decoded, int_to_char, blank_index=blank_index)))

if __name__ == "__main__":
    if args.mode == "train":
        train(num_classes)
    if args.mode == "test":
        test(num_classes)