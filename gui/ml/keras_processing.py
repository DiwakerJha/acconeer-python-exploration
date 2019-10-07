from keras.models import Model
from keras import backend as K
from keras.layers import (Dense, Dropout, Input, GaussianNoise, Activation, Conv1D, Conv2D,
                          MaxPool2D, Flatten, BatchNormalization)
from keras.utils import to_categorical
from keras.callbacks import EarlyStopping, LambdaCallback, ModelCheckpoint
from sklearn.model_selection import train_test_split

import numpy as np
import argparse

from acconeer_utils import example_utils
from helper import ErrorFormater
import tensorflow as tf


class MachineLearning():
    def __init__(self, model_dimension=2):
        self.labels_dict = None
        self.model = None
        self.validation_hist = False
        self.model_dimensions = {
            "dimensionality": model_dimension,
            "input": None,
            "output": None,
            "init_shape":  None,
        }
        self.format_error = ErrorFormater()
        self.model_params = None

    def set_model_dimensionality(self, dim):
        if isinstance(dim, int):
            if dim > 0 and dim < 3:
                self.model_dimensions["dimensionality"] = dim
        else:
            print("Incorrect dimension input ", dim)

    def init_model_1D(self, input_dimensions):
        print("\nInitiating 1D model with {:d} inputs and {:d} outputs".format(input_dimensions[0],
                                                                               self.label_num))

        inputs = Input(shape=input_dimensions)

        use_cnn = True
        if use_cnn:
            x = Conv1D(filters=32, kernel_size=12, activation="relu", padding="same")(inputs)
            x = Conv1D(filters=32, kernel_size=8, activation="relu", padding="same")(x)
            x = Conv1D(filters=32, kernel_size=4, activation="relu", padding="same")(x)
            x = Dropout(rate=0.25)(x)
            x = Conv1D(filters=32, kernel_size=2, activation="relu", padding="same")(x)
            x = Flatten()(x)
        else:
            x = Dense(64, activation=None)(inputs)
        x = GaussianNoise(0.1)(x)
        x = Activation(activation="relu")(x)
        x = Dense(64, activation="relu")(x)
        x = Dropout(rate=0.25)(x)
        x = Dense(64, activation="relu")(x)
        x = Dense(64, activation="relu")(x)

        predictions = Dense(self.label_num, activation="softmax")(x)

        self.model = Model(inputs=inputs, outputs=predictions)

        self.model.compile(
            loss="categorical_crossentropy",
            optimizer="adam",
            metrics=["accuracy"]
        )

    def init_model_2D(self, input_dimensions):
        self.y_dim = input_dimensions[0]
        self.x_dim = input_dimensions[1]
        print("\nInitiating 2d model with {:d}x{:d} inputs"
              " and {:d} outputs".format(self.y_dim, self.x_dim,
                                         self.label_num))
        inputs = Input(shape=input_dimensions)

        x = Conv2D(filters=32, kernel_size=(3, 3), activation="relu")(inputs)
        x = self.maxpool(x)
        x = GaussianNoise(0.3)(x)
        x = Dropout(rate=0.1)(x)
        x = Conv2D(filters=64, kernel_size=(2, 2), activation="relu")(x)
        x = self.maxpool(x)
        x = Conv2D(filters=128, kernel_size=(2, 2), activation="relu")(x)
        x = self.maxpool(x)
        x = Conv2D(filters=128, kernel_size=(2, 2), activation="relu")(x)
        x = BatchNormalization()(x)
        x = self.maxpool(x)
        x = Flatten()(x)
        x = Dropout(rate=0.5)(x)
        predictions = Dense(self.label_num, activation="softmax")(x)

        self.model = Model(inputs=inputs, outputs=predictions)

        self.model.compile(
            loss="categorical_crossentropy",
            optimizer="adam",
            metrics=["accuracy"]
        )

    def maxpool(self, x):
        x_pool = y_pool = 2
        if self.y_dim <= 9:
            y_pool = 1
        if self.x_dim <= 9:
            x_pool = 1

        self.x_dim /= x_pool
        self.y_dim /= y_pool

        return MaxPool2D(pool_size=(y_pool, x_pool))(x)

    def train(self, x, y, epochs=128, batch_size=128, eval_data=None, save_best=None,
              dropout=False, learning_rate=None, cb_func=None):
        if eval_data:
            if isinstance(eval_data, float):
                x, xTest, y, yTest = train_test_split(x, y, test_size=eval_data)
                eval_data = (xTest, yTest)
            self.validation_hist = True

        cb = []
        if cb_func:
            if isinstance(cb_func, list):
                for f in cb_func:
                    func = LambdaCallback(on_epoch_end=lambda epoch, logs: f(logs))
                    cb.append(func)
            else:
                func = LambdaCallback(on_epoch_end=lambda epoch, logs: cb_func(logs))
                cb.append(func)
        if isinstance(dropout, dict):
            if dropout["monitor"] in ["acc", "val_acc", "loss", "val_loss"]:
                cb_early_stop = EarlyStopping(monitor=dropout["monitor"],
                                              min_delta=dropout["min_delta"],
                                              patience=dropout["patience"],
                                              verbose=0,
                                              mode="auto")
                cb.append(cb_early_stop)
        if save_best:
            cb_best = ModelCheckpoint(save_best, monitor="val_acc", verbose=0,
                                      save_best_only=True, save_weights_only=False,
                                      mode="auto", period=1)
            cb.append(cb_best)

        if learning_rate is not None:
            K.set_value(self.model.optimizer.lr, learning_rate)

        with self.tf_session.as_default():
            with self.tf_graph.as_default():
                history = self.model.fit(x, y, epochs=epochs, batch_size=batch_size,
                                         callbacks=cb, validation_data=eval_data)

        if save_best:
            self.save_info(save_best)

        return history

    def set_learning_rate(self, rate):
        K.set_value(self.model.optimizer.lr, rate)

    def eval(self, x, y):
        with self.tf_session.as_default():
            with self.tf_graph.as_default():
                test_loss, test_acc = self.model.evaluate(x, y)
                print("\nTest result:")
                print("Loss: ", test_loss, "Accuracy: ", test_acc)

    def predict(self, x):
        if len(x.shape) == len(self.model.input_shape) - 1:
            if x.shape[0] == self.model.input_shape[1]:
                x = np.expand_dims(x, 0)
            else:
                x = np.expand_dims(x, len(x.shape))
        if len(x.shape) == len(self.model.input_shape) - 2:
            x = np.expand_dims(x, 0)
            x = np.expand_dims(x, len(x.shape))

        if len(x.shape) != len(self.model.input_shape):
            print("Wrong data shapes:\n Model: {}\n Test: {}\n".format(self.model.input_shape,
                                                                       x.shape,))
            return None

        with self.tf_graph.as_default():
            with self.tf_session.as_default():
                prediction = self.model.predict(x)

        result = list()
        for pred in prediction:
            res = {}
            category = {}
            for p in range(len(pred)):
                category[self.labelnum2text(p, self.labels_dict)] = [pred[p], p]
            res["label_predictions"] = category
            res["number_labels"] = len(pred)
            res["prediction"] = self.labelnum2text(np.argmax(pred), self.labels_dict)
            res["confidence"] = max(pred)
            res["label_num"] = np.argmax(pred)
            result.append(res)
        return result

    def label_conversion(self, labels):
        labels_dict = {}
        label_num = 0
        converted_labels = np.zeros(len(labels))
        for i, label in enumerate(labels):
            try:
                labels_dict[label]
            except Exception:
                labels_dict[label] = label_num
                label_num += 1
            converted_labels[i] = labels_dict[label]
        return converted_labels, label_num, labels_dict

    def label_assignment(self, labels, labels_dict):
        assigned_labels = np.zeros(len(labels))
        for i, label in enumerate(labels):
            assigned_labels[i] = labels_dict[label]
        return assigned_labels

    def labelnum2text(self, num, label_dict):
        for key in label_dict:
            if label_dict[key] == num:
                return key
        return None

    def load_train_data(self, files, model_exists=False, load_test_data=False):
        err_tip = "<br>Try clearing training before loading more data!"
        data = []
        configs = []
        feature_lists = []
        frame_settings_list = []
        feature_map_dims = []
        for file in files:
            file_data = np.load(file, allow_pickle=True).item()
            data.append(file_data)
            configs.append(file_data["frame_data"]["sensor_config"])
            feature_lists.append(file_data["feature_list"])
            frame_settings_list.append(file_data["frame_settings"])
            feature_map_dims.append(
                file_data["frame_data"]["ml_frame_data"]["frame_list"][0]["feature_map"].shape
                )

        data_type = "training"
        if load_test_data:
            if self.labels_dict is None:
                return {"data": data, "success": False, "message": "Load train data first"}
            data_type = "test"

        if data_type == "training":
            self.model_params = {
                "feature_list": feature_lists[0],
                "frame_settings": frame_settings_list[0],
                "sensor_config": configs[0],
                "model_dimensions": self.model_dimensions,
                }
            if model_exists:
                self.model_dimensions["input"] = self.model.input_shape[1:-1]
                self.model_dimensions["output"] = self.model.output_shape[-1]
            else:
                self.model_dimensions["dimensionality"] = 2
                self.model_dimensions["input"] = feature_map_dims[0]
                if feature_map_dims[0][1] == 1:
                    self.model_dimensions["dimensionality"] = 1
        else:
            if self.model_params is None:
                message = "Load training data first!"
                return {"success": False, "message": message}

        for i in range(1, len(files)):
            # TODO: Check that files are compatible
            map_dims = self.model_dimensions["input"]
            if map_dims != feature_map_dims[i]:
                message = "Input dimenions not matching: <br> Model {} - Data {}".format(
                    map_dims,
                    feature_map_dims[i])
                message += err_tip
                return {"success": False, "message": message}

        labels = []
        feature_maps = []
        for d in data:
            fdata = d["frame_data"]["ml_frame_data"]["frame_list"]
            for data_idx in fdata:
                feature_maps.append(data_idx["feature_map"])
                labels.append(data_idx["label"])

        feature_map_data = np.stack(feature_maps)
        if self.model_dimensions["dimensionality"] == 2:
            feature_map_data = np.expand_dims(
                feature_map_data,
                self.model_dimensions["dimensionality"] + 1)

        if data_type == "training":
            data_labels, self.label_num, self.labels_dict = self.label_conversion(labels)
            if not model_exists:
                self.model_dimensions["output"] = self.label_num
            else:
                output = self.model_dimensions["output"]
                if self.label_num != output:
                    message = "Output dimenions not matching: <br> Model {} - Data {}".format(
                        output,
                        self.label_num)
                    message += err_tip
                    return {"success": False, "message": message}
        else:
            data_labels = self.label_assignment(labels, self.labels_dict)

        label_categories = to_categorical(data_labels, self.label_num)

        if data_type == "training":
            self.model_dimensions["init_shape"] = feature_map_data.shape[1:]
            print(self.model_dimensions)
            if not model_exists:
                self.clear_model(reinit=True)

        message = "Loaded {} data with shape {}<br>".format(data_type, feature_map_data.shape)
        message += "Found labels:<br>"
        for label in self.labels_dict:
            message += label + "<br>"

        data = {
            "x_data": feature_map_data,
            "y_labels": label_categories,
            "label_list": self.get_label_list(),
            "feature_list": self.model_params["feature_list"],
            "sensor_config": self.model_params["sensor_config"],
            "frame_settings": self.model_params["frame_settings"],
            "model_dimensions": self.model_params["model_dimensions"],
        }
        return {"data": data, "success": True, "message": message}

    def load_test_data(self, files):
        return self.load_train_data(files, load_test_data=True)

    def save_model(self, file, feature_list, sensor_config, frame_settings):
        try:
            info = {
                "labels_dict": self.labels_dict,
                "model_dimensions": self.model_dimensions,
                "feature_list": feature_list,
                "sensor_config": sensor_config,
                "model": self.model,
                "frame_settings": frame_settings,
            }
            np.save(file, info)
        except Exception as e:
            message = "Error saving model:<br>{}".format(e)
        else:
            message = None

        return message

    def load_model(self, file):
        try:
            del self.model
            info = np.load(file, allow_pickle=True)
            self.model = info.item()["model"]
            self.labels_dict = info.item()["labels_dict"]
            self.model_dimensions = info.item()["model_dimensions"]
            self.label_num = self.model_dimensions["output"]
            feature_list = info.item()["feature_list"]
            sensor_config = info.item()["sensor_config"]
            frame_settings = info.item()["frame_settings"]
            self.tf_session = K.get_session()
            self.tf_graph = tf.get_default_graph()
            with self.tf_session.as_default():
                with self.tf_graph.as_default():
                    self.model._make_predict_function()
        except Exception as e:
            error_text = self.format_error.error_to_text(e)
            message = "Error in load model:<br>{}".format(error_text)
            return {
                "loaded": False,
                "message": message,
                }
        else:
            message = "Loaded model with input shape:<br>{}<br>".format(self.model.input_shape)
            message += "Using {} features.".format(len(feature_list))

        return {
            "loaded": True,
            "message": message,
            "feature_list": feature_list,
            "sensor_config": sensor_config,
            "frame_settings": frame_settings,
            }

    def clear_model(self, reinit=False):
        if self.model is not None:
            K.clear_session()
            del self.model
            self.model = None

        if reinit and self.model_dimensions is not None:
            model_shape = self.model_dimensions["init_shape"]
            self.tf_session = K.get_session()
            self.tf_graph = tf.get_default_graph()
            with self.tf_session.as_default():
                with self.tf_graph.as_default():
                    if self.model_dimensions["dimensionality"] == 1:
                        self.init_model_1D(model_shape)
                    else:
                        self.init_model_2D(model_shape)

    def get_current_session(self, graph=None):
        return self.tf_session

    def get_current_graph(self):
        return self.tf_graph

    def set_current_session(self, session):
        K.set_session(session)

    def threaded_training(self, train_params, epochs=1):
        tf_session = train_params["session"]
        tf_graph = train_params["graph"]
        with tf_session.as_default():
            with tf_graph.as_default():
                self.train(
                    train_params["x"],
                    train_params["y"],
                    epochs=epochs,
                    batch_size=train_params["batch_size"],
                    eval_data=train_params["eval_data"],
                    save_best=train_params["save_best"],
                    dropout=train_params["dropout"],
                    cb_func=train_params["cb"]
                    )
        return self.model, self.get_current_graph(), self.get_current_session()

    def clear_training_data(self):
        self.model_params = None
        self.clear_model()

    def get_labels(self):
        return self.labels_dict

    def get_label_list(self):
        label_list = list()
        for i in range(len(self.labels_dict)):
            for key in self.labels_dict:
                if self.labels_dict[key] == i:
                    label_list.append(key)
        return label_list

    def confusion_matrix(self, y_test, predictions, print_to_cmd=False):
        matrix = np.zeros((self.label_num, self.label_num), dtype=int)
        for idx, p in enumerate(predictions):
            matrix[int(np.argmax(y_test[idx])), int(p["label_num"])] += 1
        row_labels = []
        max_len = 0
        for i in range(matrix.shape[0]):
            for key in self.labels_dict:
                if self.labels_dict[key] == i:
                    row_labels.append(key)
                    if len(key) > max_len:
                        max_len = len(key)

        if print_to_cmd:
            print("")
            for row_label, row in zip(row_labels, matrix):
                print("%s [%s]" % (row_label.ljust(max_len),
                                   " ".join("%09s" % i for i in row)))
            print("%s %s" % ("".ljust(max_len),
                             " ".join("%s" % i.ljust(11) for i in row_labels)))

        return {"matrix": matrix, "labels": row_labels}


class KerasPlotting:
    def __init__(self):
        self.first = True
        self.history = {
            "acc": [],
            "loss": [],
            "val_acc": [],
            "val_loss": [],
        }

    def setup(self, win):
        win.setWindowTitle("Keras training results")

        self.train_plot_window = win.addPlot(row=0, col=0, title="Training results")
        self.train_plot_window.showGrid(x=True, y=True)
        self.train_plot_window.addLegend(offset=(-10, 10))
        self.train_plot_window.setYRange(0, 1)
        self.train_plot_window.setLabel("left", "Accuracy/Loss")
        self.train_plot_window.setLabel("bottom", "Epoch")

        self.test_plot_window = win.addPlot(row=1, col=0, title="Test-set results")
        self.test_plot_window.showGrid(x=True, y=True)
        self.test_plot_window.addLegend(offset=(-10, 10))
        self.test_plot_window.setYRange(0, 1)
        self.test_plot_window.setLabel("left", "Accuracy/Loss")
        self.test_plot_window.setLabel("bottom", "Epoch")

        pen = example_utils.pg_pen_cycler(1)
        self.train_acc_plot = self.train_plot_window.plot(pen=pen, name="Accuracy")
        self.test_acc_plot = self.test_plot_window.plot(pen=pen, name="Accuracy")
        pen = example_utils.pg_pen_cycler(2)
        self.train_loss_plot = self.train_plot_window.plot(pen=pen, name="Loss")
        self.test_loss_plot = self.test_plot_window.plot(pen=pen, name="Loss")

    def process(self, data=None, flush_data=False):
        if flush_data:
            for hist in self.history:
                self.history[hist] = []

        if data is not None:
            for key in data:
                if key not in self.history:
                    self.history[key] = []
                self.history[key].append(data[key])

        self.update(self.history, from_process=True)

    def update(self, data, from_process=False):
        if data is None:
            return

        history = data
        if not from_process:
            history = data.history

        for key in history:
            if "val_acc" in key:
                self.train_acc_plot.setData(history[key])
            elif "val_loss" in key:
                self.train_loss_plot.setData(history[key])
            elif "acc" in key:
                self.test_acc_plot.setData(history[key])
            elif "loss" in key:
                self.test_loss_plot.setData(history[key])


class Arguments():
    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("-l", "--load", dest="load",
                            help="Load training data", default="")
        parser.add_argument("-e", "--evaluate", dest="evaluate",
                            help="Sensor", default="")
        parser.add_argument("-sb", "--save-best", dest="save_best",
                            help="Save model", default=None)
        parser.add_argument("-s", "--save", dest="save",
                            help="Save model", default=None)
        parser.add_argument("-m", "--model", dest="model",
                            help="Load model", default=None)
        parser.add_argument("-t", "--train", dest="train",
                            help="Sensor", action="store_true")

        args = parser.parse_args()
        self.load = args.load
        self.save = args.save
        self.save_best = args.save_best
        self.train = args.train
        self.evaluate = args.evaluate
        self.model = args.model

    def get_args(self):
        return self


if __name__ == "__main__":
    arg = Arguments()
    args = arg.get_args()

    # TODO: add code for Deep learning without GUI
