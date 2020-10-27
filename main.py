import sys
import threading
import time

import cv2
from PySide2.QtCore import QRect
from PySide2.QtGui import (QPainter, QBrush, QColor, QImage, QPixmap, Qt, QFont,
                           QPen, QIcon)
from PySide2.QtWidgets import (QMainWindow, QPushButton, QVBoxLayout,
                               QHBoxLayout, QWidget, QGroupBox, QLabel,
                               QLineEdit, QApplication, QFileDialog, QCheckBox,
                               QComboBox, QGridLayout, QListView, QDoubleSpinBox)

import msg_box
from gb import GLOBAL
from yolo import YOLO5


def thread_runner(func):
    """多线程"""

    def wrapper(*args, **kwargs):
        threading.Thread(target=func, args=args, kwargs=kwargs).start()

    return wrapper


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('YOLOv5 Object Detection')
        self.setWindowIcon(QIcon('img/yologo.png'))
        self.setMinimumSize(1200, 800)

        GLOBAL.init_config()

        self.camera = WidgetCamera()  # 摄像头
        self.config = WidgetConfig()  # Yolo配置界面

        self.btn_camera = QPushButton('开启/关闭摄像头')  # 开启或关闭摄像头
        self.btn_camera.setFixedHeight(60)
        vbox1 = QVBoxLayout()
        vbox1.addWidget(self.config)
        vbox1.addStretch()
        vbox1.addWidget(self.btn_camera)

        self.btn_camera.clicked.connect(self.oc_camera)

        hbox = QHBoxLayout()
        hbox.addWidget(self.camera, 3)
        hbox.addLayout(vbox1, 1)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox)

        self.central_widget = QWidget()
        self.central_widget.setLayout(vbox)

        self.setCentralWidget(self.central_widget)
        self.show()

    def oc_camera(self):
        if self.camera.cap.isOpened():
            self.camera.close_camera()  # 关闭摄像头
        else:
            ret = self.camera.open_camera(
                use_camera=self.config.check_camera.isChecked(),
                video=self.config.line_video.text()
            )
            if ret:
                fps = 0 if self.config.check_camera.isChecked() else 30
                self.camera.show_camera(fps=fps)
                if self.reload_yolo():
                    self.camera.start_detect()

    def reload_yolo(self):
        """重新加载YOLO模型"""
        # 目标检测
        self.config.save_config()
        check = self.camera.yolo.set_config(
            weights=self.config.line_weights.text(),
            device=self.config.line_device.text(),
            img_size=self.config.combo_size.currentData(),
            conf=round(self.config.spin_conf.value(), 1),
            iou=round(self.config.spin_iou.value(), 1),
            agnostic=self.config.check_agnostic.isChecked(),
            augment=self.config.check_augment.isChecked()
        )
        if not check:
            msg = msg_box.MsgWarning()
            msg.setText('配置信息有误，无法正常加载YOLO模型！')
            msg.exec()
            self.camera.stop_detect()  # 关闭摄像头
            return False
        self.camera.yolo.load_model()
        return True

    def resizeEvent(self, event):
        self.update()

    def closeEvent(self, event):
        if self.camera.cap.isOpened():
            self.camera.close_camera()


class WidgetCamera(QWidget):
    def __init__(self):
        super(WidgetCamera, self).__init__()

        self.yolo = YOLO5()

        self.opened = False  # 摄像头已打开
        self.detecting = False  # 目标检测中
        self.cap = cv2.VideoCapture()

        self.pix_image = None  # QPixmap视频帧
        self.image = None  # 当前读取到的图片
        self.scale = 1  # 比例
        self.objects = []

        self.fps = 0  # 帧率

    def open_camera(self, use_camera, video):
        """打开摄像头，成功打开返回True"""
        cam = 0  # 默认摄像头
        if not use_camera:
            cam = video  # 视频流文件
        flag = self.cap.open(cam)  # 打开camera
        if flag:
            self.opened = True  # 已打开
            return True
        else:
            msg = msg_box.MsgWarning()
            msg.setText('视频流开启失败！\n'
                        '请确保摄像头已打开或视频文件真实存在！')
            msg.exec()
            return False

    def close_camera(self):
        self.opened = False  # 先关闭目标检测线程再关闭摄像头
        self.stop_detect()  # 停止目标检测线程
        time.sleep(0.1)  # 等待读取完最后一帧画面，读取一帧画面0.1s以内，一般0.02~0.03s
        self.cap.release()
        self.reset()  # 恢复初始状态

    @thread_runner
    def show_camera(self, fps=0):
        """传入参数帧率，摄像头使用默认值0，视频一般取30|60"""
        print('显示画面线程开始')
        wait = 1 / fps if fps else 0
        while self.opened:
            self.read_image()  # 0.1s以内，一般0.02~0.03s
            if fps:
                time.sleep(wait)  # 等待wait秒读取一帧画面并显示
            self.update()
        self.update()
        print('显示画面线程结束')

    def read_image(self):
        ret, image = self.cap.read()
        if ret:
            # 删去最后一层
            if image.shape[2] == 4:
                image = image[:, :, :-1]
            self.image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)  # image

    @thread_runner
    def start_detect(self):
        # 初始化yolo参数
        self.detecting = True
        print('目标检测线程开始')
        while self.detecting:
            if self.image is None:
                continue
            # 检测
            t0 = time.time()
            self.objects = self.yolo.obj_detect(self.image)
            t1 = time.time()
            self.fps = 1 / (t1 - t0)
            self.update()
        self.update()
        print('目标检测线程结束')

    def stop_detect(self):
        """停止目标检测"""
        self.detecting = False

    def reset(self):
        """恢复初始状态"""
        self.opened = False  # 摄像头关闭
        self.pix_image = None  # 无QPixmap视频帧
        self.image = None  # 当前无读取到的图片
        self.scale = 1  # 比例无
        self.objects = []  # 无检测到的目标
        self.fps = 0  # 帧率无

    def resizeEvent(self, event):
        self.update()

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        self.draw(qp)
        qp.end()

    def draw(self, qp):
        qp.setWindow(0, 0, self.width(), self.height())  # 设置窗口
        qp.setRenderHint(QPainter.SmoothPixmapTransform)
        # 画框架背景
        qp.setBrush(QColor('#cecece'))  # 框架背景色
        qp.setPen(Qt.NoPen)
        rect = QRect(0, 0, self.width(), self.height())
        qp.drawRect(rect)

        sw, sh = self.width(), self.height()  # 图像窗口宽高

        if not self.opened:
            qp.drawPixmap(sw / 2 - 100, sh / 2 - 100, 200, 200, QPixmap('img/video.svg'))

        # 画图
        if self.opened and self.image is not None:
            ih, iw, _ = self.image.shape
            self.scale = sw / iw if sw / iw < sh / ih else sh / ih  # 缩放比例
            px = round((sw - iw * self.scale) / 2)
            py = round((sh - ih * self.scale) / 2)
            qimage = QImage(self.image.data, iw, ih, 3 * iw, QImage.Format_RGB888)  # 转QImage
            qpixmap = QPixmap.fromImage(qimage.scaled(sw, sh, Qt.KeepAspectRatio))  # 转QPixmap
            pw, ph = qpixmap.width(), qpixmap.height()  # 缩放后的QPixmap大小
            qp.drawPixmap(px, py, qpixmap)

            font = QFont()
            font.setFamily('Microsoft YaHei')
            if self.fps > 0:
                font.setPointSize(14)
                qp.setFont(font)
                pen = QPen()
                pen.setColor(Qt.white)
                qp.setPen(pen)
                qp.drawText(sw - px - 150, py + 40, 'FPS: ' + str(round(self.fps, 2)))

            # 画目标框
            pen = QPen()
            pen.setWidth(2)  # 边框宽度
            for obj in self.objects:
                font.setPointSize(10)
                qp.setFont(font)
                rgb = [round(c) for c in obj['color']]
                pen.setColor(QColor(rgb[0], rgb[1], rgb[2]))  # 边框颜色
                brush1 = QBrush(Qt.NoBrush)  # 内部不填充
                qp.setBrush(brush1)
                qp.setPen(pen)
                # 坐标 宽高
                ox, oy = px + round(pw * obj['x']), py + round(ph * obj['y'])
                ow, oh = round(pw * obj['w']), round(ph * obj['h'])
                obj_rect = QRect(ox, oy, ow, oh)
                qp.drawRect(obj_rect)  # 画矩形框

                # 画 类别 和 置信度
                qp.drawText(ox, oy - 5, str(obj['class']) + str(round(obj['confidence'], 2)))


class WidgetConfig(QGroupBox):
    def __init__(self):
        super(WidgetConfig, self).__init__()

        HEIGHT = 30

        grid = QGridLayout()

        # 使用默认摄像头复选框
        self.check_camera = QCheckBox('Use default camera')
        self.check_camera.setChecked(True)
        self.check_camera.stateChanged.connect(self.slot_check_camera)

        grid.addWidget(self.check_camera, 0, 0, 1, 3)  # 一行三列

        # 选择视频文件
        label_video = QLabel('Source')
        self.line_video = QLineEdit()
        self.line_video.setFixedHeight(HEIGHT)
        self.line_video.setEnabled(False)
        self.line_video.setText(GLOBAL.config.get('video', ''))
        self.line_video.editingFinished.connect(
            lambda: GLOBAL.record_config({'video': self.line_video.text()}))

        self.btn_video = QPushButton('...')
        self.btn_video.setFixedWidth(40)
        self.btn_video.setFixedHeight(HEIGHT)
        self.btn_video.setEnabled(False)
        self.btn_video.clicked.connect(self.choose_video_file)

        self.slot_check_camera()

        grid.addWidget(label_video, 1, 0)
        grid.addWidget(self.line_video, 1, 1)
        grid.addWidget(self.btn_video, 1, 2)

        # 选择权重文件
        label_weights = QLabel('Weights')
        self.line_weights = QLineEdit()
        self.line_weights.setFixedHeight(HEIGHT)
        self.line_weights.setText(GLOBAL.config.get('weights', ''))
        self.line_weights.editingFinished.connect(lambda: GLOBAL.record_config(
            {'weights': self.line_weights.text()}
        ))

        self.btn_weights = QPushButton('...')
        self.btn_weights.setFixedWidth(40)
        self.btn_weights.setFixedHeight(HEIGHT)
        self.btn_weights.clicked.connect(self.choose_weights_file)

        grid.addWidget(label_weights, 2, 0)
        grid.addWidget(self.line_weights, 2, 1)
        grid.addWidget(self.btn_weights, 2, 2)

        # 是否使用GPU
        label_device = QLabel('CUDA device')
        self.line_device = QLineEdit('cpu')
        self.line_device.setText(GLOBAL.config.get('device', 'cpu'))
        self.line_device.setPlaceholderText('cpu or 0 or 0,1,2,3')
        self.line_device.setFixedHeight(HEIGHT)
        self.line_device.editingFinished.connect(lambda: GLOBAL.record_config(
            {'device': self.line_device.text()}
        ))

        grid.addWidget(label_device, 3, 0)
        grid.addWidget(self.line_device, 3, 1, 1, 2)

        # 设置图像大小
        label_size = QLabel('Img Size')
        self.combo_size = QComboBox()
        self.combo_size.setFixedHeight(HEIGHT)
        self.combo_size.setStyleSheet(
            'QAbstractItemView::item {height: 40px;}')
        self.combo_size.setView(QListView())
        self.combo_size.addItem('320', 320)
        self.combo_size.addItem('416', 416)
        self.combo_size.addItem('480', 480)
        self.combo_size.addItem('544', 544)
        self.combo_size.addItem('640', 640)
        self.combo_size.setCurrentIndex(
            self.combo_size.findData(GLOBAL.config.get('img_size', 480)))
        self.combo_size.currentIndexChanged.connect(lambda: GLOBAL.record_config(
            {'img_size': self.combo_size.currentData()}))

        grid.addWidget(label_size, 4, 0)
        grid.addWidget(self.combo_size, 4, 1, 1, 2)

        # 设置置信度阈值
        label_conf = QLabel('Confidence')
        self.spin_conf = QDoubleSpinBox()
        self.spin_conf.setFixedHeight(HEIGHT)
        self.spin_conf.setDecimals(1)
        self.spin_conf.setRange(0.1, 0.9)
        self.spin_conf.setSingleStep(0.1)
        self.spin_conf.setValue(GLOBAL.config.get('conf_thresh', 0.5))
        self.spin_conf.valueChanged.connect(lambda: GLOBAL.record_config(
            {'conf_thresh': round(self.spin_conf.value(), 1)}
        ))

        grid.addWidget(label_conf, 5, 0)
        grid.addWidget(self.spin_conf, 5, 1, 1, 2)

        # 设置IOU阈值
        label_iou = QLabel('IOU')
        self.spin_iou = QDoubleSpinBox()
        self.spin_iou.setFixedHeight(HEIGHT)
        self.spin_iou.setDecimals(1)
        self.spin_iou.setRange(0.1, 0.9)
        self.spin_iou.setSingleStep(0.1)
        self.spin_iou.setValue(GLOBAL.config.get('iou_thresh', 0.5))
        self.spin_iou.valueChanged.connect(lambda: GLOBAL.record_config(
            {'iou_thresh': round(self.spin_iou.value(), 1)}
        ))

        grid.addWidget(label_iou, 6, 0)
        grid.addWidget(self.spin_iou, 6, 1, 1, 2)

        # class-agnostic NMS
        self.check_agnostic = QCheckBox('Agnostic')
        self.check_agnostic.setChecked(GLOBAL.config.get('agnostic', True))
        self.check_agnostic.stateChanged.connect(lambda: GLOBAL.record_config(
            {'agnostic': self.check_agnostic.isChecked()}
        ))

        grid.addWidget(self.check_agnostic, 7, 0, 1, 3)  # 一行三列

        # augmented inference
        self.check_augment = QCheckBox('Augment')
        self.check_augment.setChecked(GLOBAL.config.get('augment', True))
        self.check_augment.stateChanged.connect(lambda: GLOBAL.record_config(
            {'augment': self.check_augment.isChecked()}
        ))

        grid.addWidget(self.check_augment, 8, 0, 1, 3)  # 一行三列

        self.setLayout(grid)  # 设置布局

    def slot_check_camera(self):
        check = self.check_camera.isChecked()
        GLOBAL.record_config({'use_camera': check})  # 保存配置
        if check:
            self.line_video.setEnabled(False)
            self.btn_video.setEnabled(False)
        else:
            self.line_video.setEnabled(True)
            self.btn_video.setEnabled(True)

    def choose_weights_file(self):
        """从系统中选择权重文件"""
        file = QFileDialog.getOpenFileName(self, "Pre-trained YOLOv5 Weights", "./",
                                           "Weights Files (*.pt);;All Files (*)")
        if file[0] != '':
            self.line_weights.setText(file[0])
            GLOBAL.record_config({'weights': file[0]})

    def choose_video_file(self):
        """从系统中选择视频文件"""
        file = QFileDialog.getOpenFileName(self, "Video Files", "./",
                                           "Video Files (*)")
        if file[0] != '':
            self.line_video.setText(file[0])
            GLOBAL.record_config({'video': file[0]})

    def save_config(self):
        """保存当前的配置到配置文件"""
        config = {
            'use_camera': self.check_camera.isChecked(),
            'video': self.line_video.text(),
            'weights': self.line_weights.text(),
            'device': self.line_device.text(),
            'img_size': self.combo_size.currentData(),
            'conf_thresh': round(self.spin_conf.value(), 1),
            'iou_thresh': round(self.spin_iou.value(), 1),
            'agnostic': self.check_agnostic.isChecked(),
            'augment': self.check_augment.isChecked()
        }
        GLOBAL.record_config(config)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
