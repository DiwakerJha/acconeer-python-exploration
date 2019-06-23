import numpy as np
from PyQt5 import QtCore
import pyqtgraph as pg

from acconeer_utils.clients import configs
from acconeer_utils import example_utils

import logging

log = logging.getLogger("acconeer_utils.examples.gui_envelope")


def get_processing_config():
    return {
        "image_buffer": {
            "name": "Image history",
            "value": 100,
            "limits": [10, 16384],
            "type": int,
            "text": None,
        },
        "averaging": {
            "name": "Averaging",
            "value": 0,
            "limits": [0, 0.9999],
            "type": float,
            "text": None,
        },
    }


def get_sensor_config():
    config = configs.EnvelopeServiceConfig()
    config.range_interval = [0.1, 0.5]
    config.sweep_rate = 60
    config.gain = 0.7
    return config


class EnvelopeProcessor:
    def __init__(self, sensor_config, processing_config):
        self.data_processing = processing_config["processing_handle"]
        self.sensor_config = sensor_config
        self.mode = self.sensor_config.mode
        self.start_x = self.sensor_config.range_interval[0]
        self.stop_x = self.sensor_config.range_interval[1]
        self.sweep = 0
        self.time_filter = processing_config["averaging"]["value"]

        if "create_clutter" in processing_config:
            self.create_cl = processing_config["create_clutter"]
            self.use_cl = processing_config["use_clutter"]
            self.cl_file = processing_config["clutter_file"]
            self.sweeps = processing_config["sweeps_requested"]
        else:
            self.create_cl = None
            self.use_cl = None
            self.cl_file = None
            self.sweeps = -1

        self.rate = 1/self.sensor_config.sweep_rate

        self.image_buffer = processing_config["image_buffer"]["value"]

        self.peak_history = np.zeros(self.image_buffer, dtype="float")

        if self.sweeps < 0:
            self.sweeps = self.image_buffer

        if self.create_cl:
            self.sweeps = max(self.sweeps, 100)

    def update_processing_config(self, processing_config):
        self.use_cl = processing_config["use_clutter"]

    def process(self, sweep):
        snr = {}
        peak_data = {}
        self.data_len = sweep.size

        if self.sweep == 0:
            self.num_sensors = 1
            if len(sweep.shape) > 1:
                self.data_len = sweep.shape[1]
                self.num_sensors = sweep.shape[0]
            self.env_x_mm = np.linspace(self.start_x, self.stop_x, self.data_len)*1000

            self.cl_empty = np.zeros(self.data_len)
            self.last_env = np.zeros((self.num_sensors, self.data_len))

            if self.num_sensors == 1:
                self.cl, _, self.n_std_avg = \
                    self.data_processing.load_clutter_data(self.data_len, self.cl_file)
            else:
                self.cl = self.n_std_avg = self.cl_empty
                self.create_cl = False
                self.use_cl = False
                print("Background not supported for multiple sensors!")

            self.hist_env = np.zeros((len(self.env_x_mm), self.image_buffer))

        env = sweep.copy()

        if self.num_sensors == 1:
            env = np.expand_dims(env, 0)
        env = np.abs(env)

        for s in range(self.num_sensors):
            if self.use_cl:
                try:
                    env[s, :] = env[s, :] - self.cl
                    env[s, env[s, :] < 0] = 0
                except Exception as e:
                    log.error("Background has wrong format!\n{}".format(e))
                    self.use_cl = False
                    self.cl = np.zeros(self.data_len)

            time_filter = self.time_filter
            if time_filter >= 0:
                if self.sweep < np.ceil(1.0 / (1.0 - self.time_filter) - 1):
                    time_filter = min(1.0 - 1.0 / (self.sweep + 1), self.time_filter)
                if self.sweep:
                    env[s, :] = (1 - time_filter) * env[s, :] + time_filter * self.last_env[s, :]
                self.last_env[s, :] = env[s, :].copy()

        if self.create_cl:
            if self.sweep == 0:
                self.cl = np.zeros((self.sweeps, len(self.cl)))
            self.cl[self.sweep, :] = env[0, :]

        peak_data = {
            'peak_idx': np.zeros(self.num_sensors),
            'peak_mm': np.zeros(self.num_sensors),
            'peak_amp': np.zeros(self.num_sensors),
            'snr': np.zeros(self.num_sensors),
            }
        env_max = np.zeros(self.num_sensors)

        for s in range(self.num_sensors):
            peak_idx = np.argmax(env[s, :])
            peak_mm = self.env_x_mm[peak_idx]
            if peak_mm <= self.start_x * 1000:
                peak_mm = self.stop_x * 1000
            peak_data['peak_mm'][s] = peak_mm
            peak_data['peak_idx'][s] = peak_idx
            env_max[s] = np.max(env[s, :])
            peak_data['peak_amp'][s] = env_max[s]

            snr = None
            signal = env[s, peak_idx]
            if self.use_cl and self.n_std_avg[peak_idx] > 0:
                noise = self.n_std_avg[peak_idx]
                snr = 20*np.log10(signal / noise)
            else:
                # Simple noise estimate: noise ~ mean(envelope)
                noise = np.mean(env[s, :])
                snr = 20*np.log10(signal / noise)
            peak_data["snr"][s] = snr

        hist_plot = np.flip(self.peak_history, axis=0)
        self.peak_history = np.roll(self.peak_history, 1)
        self.peak_history[0] = peak_data['peak_mm'][0]

        self.hist_env = np.roll(self.hist_env, 1, axis=1)
        self.hist_env[:, 0] = env[0, :]

        cl = self.cl
        if self.create_cl:
            cl = self.cl[self.sweep, :]
        elif not self.use_cl:
            cl = self.cl_empty

        plot_data = {
            "iq_data": sweep,
            "env_ampl": env,
            "env_clutter": cl,
            "clutter_raw": self.cl,
            "env_max": env_max,
            "n_std_avg": self.n_std_avg,
            "hist_plot": hist_plot,
            "hist_env": self.hist_env,
            "sensor_config": self.sensor_config,
            "peaks": peak_data,
            "x_mm": self.env_x_mm,
            "cl_file": self.cl_file,
            "sweep": self.sweep,
            "num_sensors": self.num_sensors,
        }

        self.sweep += 1

        return plot_data


class PGUpdater:
    def __init__(self, sensor_config, processing_config):
        self.env_plot_max_y = 1
        self.sensor_config = sensor_config
        self.num_sensors = len(sensor_config.sensor)

    def setup(self, win):
        win.setWindowTitle("Acconeer envelope mode example")
        self.envelope_plot_window = win.addPlot(row=0, col=0, title="Envelope")
        self.envelope_plot_window.showGrid(x=True, y=True)
        self.envelope_plot_window.addLegend(offset=(-10, 10))

        self.envelope_plot = []
        self.peak_vline = []
        self.peak_text = []
        self.clutter_plot = []

        for s in range(self.num_sensors):
            pen = example_utils.pg_pen_cycler()
            self.envelope_plot.append(self.envelope_plot_window.plot(range(10),
                                      np.zeros(10), pen=pen, name="Envelope"))
            pen = pg.mkPen(0.2, width=2, style=QtCore.Qt.DotLine)
            self.clutter_plot.append(self.envelope_plot_window.plot(range(10),
                                     np.zeros(10), pen=pen, name="Background"))
            self.peak_vline.append(pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(width=2,
                                                   style=QtCore.Qt.DotLine)))
            self.envelope_plot_window.addItem(self.peak_vline[s])
            self.clutter_plot[s].setZValue(2)

            self.peak_text.append(pg.TextItem(text="", color=(1, 1, 1), anchor=(0, 1),
                                  fill="#f0f0f0"))
            self.peak_text[s].setZValue(3)
            self.envelope_plot_window.addItem(self.peak_text[s])

        self.envelope_plot_window.setYRange(0, 1)
        self.envelope_plot_window.setLabel("left", "Amplitude")
        self.envelope_plot_window.setLabel("bottom", "Distance (mm)")

        row = 1
        title = "Envelope History"
        lut = example_utils.pg_mpl_cmap("viridis")

        self.hist_plot_image = win.addPlot(row=row, col=0, title=title)
        self.hist_plot = pg.ImageItem()
        self.hist_plot.setAutoDownsample(True)

        self.hist_plot.setLookupTable(lut)
        pen = example_utils.pg_pen_cycler(1)
        self.hist_plot_image.addItem(self.hist_plot)
        self.hist_plot_image.setLabel("left", "Distance (mm)")
        self.hist_plot_image.setLabel("bottom", "Time (s)")

        self.hist_plot_peak = self.hist_plot_image.plot(range(10),
                                                        np.zeros(10),
                                                        pen=pen)

    def update(self, data):
        xstart = data["x_mm"][0]
        xend = data["x_mm"][-1]
        xdim = data["hist_env"].shape[0]
        num_sensors = data["num_sensors"]

        if data["sweep"] <= 1:
            self.env_plot_max_y = 0
            self.envelope_plot_window.setXRange(xstart, xend)

            for s in range(num_sensors):
                self.peak_text[s].setPos(xstart, 0)

            self.smooth_envelope = example_utils.SmoothMax(
                int(self.sensor_config.sweep_rate),
                tau_decay=1,
                tau_grow=0.2
                )

            yax = self.hist_plot_image.getAxis("left")
            y = np.round(np.arange(0, xdim+xdim/9, xdim/9))
            labels = np.round(np.arange(xstart, xend+(xend-xstart)/9,
                              (xend-xstart)/9))
            ticks = [list(zip(y, labels))]
            yax.setTicks(ticks)
            self.hist_plot_image.setYRange(0, xdim)

            s_buff = data["hist_env"].shape[1]
            t_buff = s_buff / data["sensor_config"].sweep_rate
            tax = self.hist_plot_image.getAxis("bottom")
            t = np.round(np.arange(0, s_buff + 1, s_buff/min(10, s_buff)))
            labels = np.round(t / s_buff * t_buff, decimals=3)
            ticks = [list(zip(t, labels))]
            tax.setTicks(ticks)

        peaks = data["peaks"]
        for s in range(num_sensors):
            peak_txt = "Peak: N/A"
            if peaks:
                self.peak_vline[s].setValue(peaks["peak_mm"][s])
                peak_txt = "Peak: %.1fmm" % peaks["peak_mm"][s]
                if np.isfinite(peaks["snr"][s]):
                    peak_txt = "Peak: %.1fmm, SNR: %.1fdB" % (peaks["peak_mm"][s], peaks["snr"][s])
                self.peak_text[s].setText(peak_txt, color=(1, 1, 1))

            max_val = max(np.max(data["env_clutter"]+data["env_ampl"][s]),
                          np.max(data["env_clutter"]))
            peak_line = np.flip((data["hist_plot"]-xstart)/(xend - xstart)*xdim, axis=0)

            self.envelope_plot[s].setData(data["x_mm"], data["env_ampl"][s] + data["env_clutter"])
            self.clutter_plot[s].setData(data["x_mm"], data["env_clutter"])

            self.envelope_plot_window.setYRange(0, self.smooth_envelope.update(max_val))

            if s == 0:
                ymax_level = min(1.5*np.max(np.max(data["hist_env"])), self.env_plot_max_y)

                self.hist_plot.updateImage(data["hist_env"].T, levels=(0, ymax_level))
                self.hist_plot_peak.setData(peak_line)
                self.hist_plot_peak.setZValue(2)

                if max_val > self.env_plot_max_y:
                    self.env_plot_max_y = 1.2 * max_val
