from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QTextEdit, QLabel, \
    QListWidget, QListWidgetItem, QMessageBox, QTabWidget, QLineEdit, QHBoxLayout, QComboBox, QDialog, QScrollArea
from PyQt5.QtBluetooth import QBluetoothDeviceDiscoveryAgent, QBluetoothSocket, QBluetoothDeviceInfo, QBluetoothUuid, \
    QBluetoothServiceInfo
import serial
import sys
import cv2
import time
import os
from pynput import keyboard
import configparser
import sqlite3
import re

class SQLiteManager:
    def __init__(self, db_file):
        self.db_file = db_file
        self.connection = None
        self.cursor = None

    def connect(self):
        try:
            self.connection = sqlite3.connect(self.db_file)
            self.cursor = self.connection.cursor()
            print("SQLite database connected successfully")
        except sqlite3.Error as e:
            print(f"SQLite connection error: {e}")

    def create_table(self):
        try:
            query = """CREATE TABLE IF NOT EXISTS ProductData (
                           id INTEGER PRIMARY KEY AUTOINCREMENT,
                           Barcode TEXT,
                           Weight TEXT,
                           PhotoPath TEXT
                       )"""
            self.cursor.execute(query)
            self.connection.commit()
            print("Table created successfully")
        except sqlite3.Error as e:
            print(f"Create table error: {e}")

    def insert_data(self, barcode, weight, photo_path):
        try:
            # Debugging statements to trace function calls
            print(f"Attempting to insert data: barcode={barcode}, weight={weight}, photo_path={photo_path}")

            # Check if barcode and photo_path are valid (not empty and not None)
            if barcode and photo_path and photo_path != 'Resim yolu yok':
                # Check if the record already exists
                self.cursor.execute("SELECT COUNT(*) FROM ProductData WHERE Barcode=? AND PhotoPath=?",
                                    (barcode, photo_path))
                count = self.cursor.fetchone()[0]

                if count == 0:
                    query = """INSERT INTO ProductData (Barcode, Weight, PhotoPath)
                            VALUES (?, ?, ?)"""
                    self.cursor.execute(query, (barcode, weight, photo_path))
                    self.connection.commit()
                    print("Data inserted successfully")
                    self.show_success_message()

                else:
                    print("Data not inserted: record already exists")
            else:
                print("Data not inserted: barcode or photo_path is invalid or empty")
        except sqlite3.Error as e:
            print(f"Insert error: {e}")

    def show_success_message(self):
        """
        Show a success message box.
        """
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setText("Başarıyla Kaydedildi!")
        msg_box.setWindowTitle("Başarılı")
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
class SerialListener(QThread):
    barcode_received = pyqtSignal(str)

    def __init__(self, port, parent=None):
        super().__init__(parent)
        self.port = port
        self.running = True
        self.barcode_data = ""

        # Keyboard listener setup
        self.keyboard_listener = keyboard.Listener(on_press=self.on_key_press)
        self.keyboard_listener.start()

    def on_key_press(self, key):
        try:
            # Assuming the key pressed is alphanumeric
            self.barcode_data += key.char
        except AttributeError:
            if key == keyboard.Key.enter:
                self.barcode_received.emit(self.barcode_data)
                self.barcode_data = ""

    def run(self):
        try:
            with serial.Serial(self.port, 9600, timeout=1) as ser:
                while self.running:
                    # Read line from serial and emit barcode signal
                    barcode = ser.readline().decode().strip()
                    if barcode:
                        self.barcode_received.emit(barcode)
        except serial.SerialException as e:
            print(f"Seri bağlantı hatası: {e}")

    def stop(self):
        self.running = False
        self.keyboard_listener.stop()


class BluetoothManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.devmode = 0  # Initialize the attribute
        self.load_config()  # Load configuration to possibly update devmode
        self.db_manager = SQLiteManager('product_data.db')
        self.db_manager.connect()
        self.db_manager.create_table()

        self.loadModelsAndRegex()


        self.newDataAvailable.connect(self.updateUI)

        self.startupTab = QWidget()
        self.scaleTab = QWidget()
        self.bluetoothBarcodeTab = QWidget()
        self.serialBarcodeTab = QWidget()



        self.initUI()

        # Initialize discovery agents for each tab
        self.discoveryAgentScale = QBluetoothDeviceDiscoveryAgent()
        self.discoveryAgentScale.deviceDiscovered.connect(self.deviceDiscoveredScale)
        self.discoveryAgentScale.finished.connect(self.discoveryFinishedScale)
        self.discoveryAgentScale.error.connect(self.deviceDiscoveryError)

        self.discoveryAgentBluetooth = QBluetoothDeviceDiscoveryAgent()
        self.discoveryAgentBluetooth.deviceDiscovered.connect(self.deviceDiscoveredBluetooth)
        self.discoveryAgentBluetooth.finished.connect(self.discoveryFinishedBluetooth)
        self.discoveryAgentBluetooth.error.connect(self.deviceDiscoveryError)

        self.socketScale = None
        self.socketBluetooth = None
        self.serialPort = None
        self.serialConnection = None
        self.selectedDeviceInfoScale = None
        self.selectedDeviceInfoBluetooth = None
        self.latest_weight = None
        self.data_list = []
        self.selected_model = None
        self.selected_model_regex = None
        self.serialListener = None
        self.success_message_shown = False
        self.data_inserted = False

    def initUI(self):
        self.setWindowTitle("Bluetooth Manager")
        self.setGeometry(100, 100, 800, 600)

        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)

        self.tabWidget = QTabWidget()
        self.tabWidget.addTab(self.startupTab, "Başlangıç")
        self.tabWidget.addTab(self.scaleTab, "Terazi")
        self.tabWidget.addTab(self.bluetoothBarcodeTab, "Bluetooth Barkod")
        self.tabWidget.addTab(self.serialBarcodeTab, "Serial Barkod")

        self.layout = QVBoxLayout(self.centralWidget)
        self.layout.addWidget(self.tabWidget)

        self.initStartupTab()
        self.initScaleTab()
        self.initBluetoothBarcodeTab()
        self.initSerialBarcodeTab()

        self.tabWidget.setTabEnabled(2, False)  # Bluetooth Barkod tab
        self.tabWidget.setTabEnabled(3, False)  # Serial Barkod tab

    def show_success_message(self, message):
        """
        Show a success message box.
        """
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setText(message)
        msg_box.setWindowTitle("Başarılı")
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()

    def reset_data_insertion_flag(self):
        """
        Reset the flag to allow data insertion again.
        """
        self.data_inserted = False

    def reset_success_message_flag(self):
        """
        Reset the flag to allow showing the success message again.
        """
        self.success_message_shown = False
    def loadModelsAndRegex(self):
        self.model_regex = {}

        config = configparser.ConfigParser()
        config.read('config.ini')

        # Load models
        for model, regex_pattern in config['models'].items():
            # Compile the regex pattern
            compiled_regex = re.compile(regex_pattern.strip('/gm'))  # Remove leading/trailing slashes and flags
            self.model_regex[model.lower()] = compiled_regex

        print(f"Loaded models and regex patterns: {self.model_regex}")

    def showModelSelectionDialog(self):
        try:
            # Create the dialog
            dialog = QDialog(self)
            dialog.setWindowTitle('Select a Model')

            layout = QVBoxLayout(dialog)

            label = QLabel('Select a model:', dialog)
            layout.addWidget(label)

            # Create a combo box to list models
            models = list(self.model_regex.keys())
            comboBox = QComboBox(dialog)
            comboBox.addItems(models)
            layout.addWidget(comboBox)

            # Create OK button
            okButton = QPushButton('OK', dialog)
            okButton.clicked.connect(lambda: self.handleModelSelection(comboBox.currentText(), dialog))
            layout.addWidget(okButton)

            dialog.setLayout(layout)
            dialog.exec_()
        except Exception as e:
            print(f"Error in showModelSelectionDialog: {e}")
            # Optionally, display a message box or handle the error appropriately

    def handleModelSelection(self, selected_model, dialog):
        self.selected_model = selected_model.lower()
        dialog.accept()  # Close the dialog

        # Get the regex pattern for the selected model
        self.selected_model_regex = self.model_regex.get(self.selected_model, None)
        if self.selected_model_regex:
            print(f"Selected model: {self.selected_model}")
            print(f"Regex pattern: {self.selected_model_regex}")
        else:
            print("Regex pattern not found for the selected model")

    def print_data_list(self):
        """
        Print the contents of the data_list to the terminal.
        """
        for data in self.data_list:
            print(data)

    def load_config(self):
        config = configparser.ConfigParser()
        config_file_path = os.path.join(os.getcwd(), "config.ini")
        config_dir = os.path.dirname(config_file_path)

        if not os.path.exists(config_file_path):
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
            print("Config file not found. Creating default config file.")
            config['Camera'] = {}
            config['SerialPort'] = {}
            config['models'] = {}
            config['devmode'] = {}

            config['Camera']['ip_address'] = ''
            config['Camera']['username'] = ''
            config['Camera']['password'] = ''

            config['SerialPort']['port'] = ''

            config['models']['HRCR'] = ''
            config['models']['GUNAS'] = ''
            config['models']['DENEME'] = ''
            config['models']['DENEME2'] = ''

            config['devmode']['on'] = '0'  # Default value for devmode

            with open(config_file_path, 'w') as configfile:
                config.write(configfile)

            print("Default config file created. Please update the configuration and restart the application.")
            sys.exit(0)

        config.read(config_file_path)

        # Check if 'models' section exists in config.ini
        if not config.has_section('models'):
            config.add_section('models')
            config.set('models', 'HRCR', '')
            config.set('models', 'GUNAS', '')
            config.set('models', 'DENEME', '')
            config.set('models', 'DENEME2', '')

            with open(config_file_path, 'w') as configfile:
                config.write(configfile)

        # Camera configuration
        self.camera_ip = config['Camera']['ip_address']
        self.camera_user = config['Camera']['username']
        self.camera_password = config['Camera']['password']

        # Serial port configuration
        self.serial_port = config['SerialPort']['port']

        # Dev mode configuration
        self.devmode = int(config['devmode'].get('on', '0'))

        if self.devmode == 1:
            print("Dev mode is ON")
        else:
            print("Dev mode is OFF")

    def initStartupTab(self):
        layout = QVBoxLayout(self.startupTab)

        # Barcode label and "No device" message
        self.barcode_label = QLabel("BARKOD: ")
        self.no_barcode_device_label = QLabel("Bağlı cihaz yok")
        barcode_layout = QHBoxLayout()
        barcode_layout.addWidget(self.barcode_label)
        barcode_layout.addWidget(self.no_barcode_device_label)
        barcode_layout.setSpacing(5)  # Adjust the spacing between the widgets
        layout.addLayout(barcode_layout)

        # Weight label and "No device" message
        self.weight_label = QLabel("AĞIRLIK: ")
        self.no_weight_device_label = QLabel("Bağlı cihaz yok")
        weight_layout = QHBoxLayout()
        weight_layout.addWidget(self.weight_label)
        weight_layout.addWidget(self.no_weight_device_label)
        weight_layout.setSpacing(5)  # Adjust the spacing between the widgets
        layout.addLayout(weight_layout)

        # Photo path label
        self.photo_path_label = QLabel("ÜRÜN RESMİ YOLU: ")
        self.photo_path_value = QLabel("Resim yolu yok")
        photo_layout = QHBoxLayout()
        photo_layout.addWidget(self.photo_path_label)
        photo_layout.addWidget(self.photo_path_value)
        photo_layout.setSpacing(5)  # Adjust the spacing between the widgets
        layout.addLayout(photo_layout)

        self.startupTab.setLayout(layout)

    def initScaleTab(self):
        layout = QVBoxLayout(self.scaleTab)

        label = QLabel("Terazi Bilgileri")
        layout.addWidget(label)

        self.labelScale = QLabel("Bulunan Cihazlar (Bluetooth Terazi):")
        layout.addWidget(self.labelScale)

        self.deviceListScale = QListWidget()
        self.deviceListScaleScrollArea = QScrollArea()
        self.deviceListScaleScrollArea.setWidget(self.deviceListScale)
        self.deviceListScaleScrollArea.setWidgetResizable(True)
        layout.addWidget(self.deviceListScaleScrollArea)

        self.startDiscoveryButtonScale = QPushButton("Cihaz Keşfi Başlat")
        self.startDiscoveryButtonScale.clicked.connect(self.startDiscoveryScale)
        layout.addWidget(self.startDiscoveryButtonScale)

        self.connectButtonScale = QPushButton("Seçilen Cihaza Bağlan")
        self.connectButtonScale.clicked.connect(self.connectToDeviceScale)
        layout.addWidget(self.connectButtonScale)

        self.disconnectButtonScale = QPushButton("Bağlantıyı Kes")
        self.disconnectButtonScale.clicked.connect(self.disconnectFromDeviceScale)
        layout.addWidget(self.disconnectButtonScale)

        self.servicesLabelScale = QLabel("Gelen Veriler (Bluetooth Terazi):")
        layout.addWidget(self.servicesLabelScale)

        # Initialize the servicesListScale as it is used in both modes
        self.servicesListScale = QTextEdit()
        self.servicesListScale.setReadOnly(True)
        self.servicesListScaleScrollArea = QScrollArea()
        self.servicesListScaleScrollArea.setWidget(self.servicesListScale)
        self.servicesListScaleScrollArea.setWidgetResizable(True)

        if self.devmode == 1:
            # Create two lists for original data and captured data
            print("Devmode çalıştı")
            self.originalDataListScale = QListWidget()
            self.originalDataListScale.setObjectName("OriginalDataList")
            self.originalDataListScaleScrollArea = QScrollArea()
            self.originalDataListScaleScrollArea.setWidget(self.originalDataListScale)
            self.originalDataListScaleScrollArea.setWidgetResizable(True)
            layout.addWidget(QLabel("Orijinal Veri"))
            layout.addWidget(self.originalDataListScaleScrollArea)

            self.capturedDataListScale = QListWidget()
            self.capturedDataListScale.setObjectName("CapturedDataList")
            self.capturedDataListScaleScrollArea = QScrollArea()
            self.capturedDataListScaleScrollArea.setWidget(self.capturedDataListScale)
            self.capturedDataListScaleScrollArea.setWidgetResizable(True)
            layout.addWidget(QLabel("Yakalanan Veri"))
            layout.addWidget(self.capturedDataListScaleScrollArea)
        else:
            # Add servicesListScale only in normal mode
            print("devmode çalışmadı")
            layout.addWidget(self.servicesListScaleScrollArea)

        # Initially disable the connect and disconnect buttons
        self.disconnectButtonScale.setEnabled(False)

    def initBluetoothBarcodeTab(self):
        layout = QVBoxLayout(self.bluetoothBarcodeTab)

        self.labelBluetooth = QLabel("Bulunan Cihazlar (Bluetooth Barkod):")
        layout.addWidget(self.labelBluetooth)

        self.deviceListBluetooth = QListWidget()
        layout.addWidget(self.deviceListBluetooth)

        self.startDiscoveryButtonBluetooth = QPushButton("Cihaz Keşfi Başlat")
        self.startDiscoveryButtonBluetooth.clicked.connect(self.startDiscoveryBluetooth)
        layout.addWidget(self.startDiscoveryButtonBluetooth)

        self.connectButtonBluetooth = QPushButton("Seçilen Cihaza Bağlan")
        self.connectButtonBluetooth.clicked.connect(self.connectToDeviceBluetooth)
        layout.addWidget(self.connectButtonBluetooth)

        self.disconnectButtonBarcode = QPushButton("Bağlantıyı Kes")
        self.disconnectButtonBarcode.clicked.connect(self.disconnectFromDeviceBarcode)
        layout.addWidget(self.disconnectButtonBarcode)

        self.servicesLabelBluetooth = QLabel("Gelen Veriler (Bluetooth Barkod):")
        layout.addWidget(self.servicesLabelBluetooth)

        self.servicesListBluetooth = QTextEdit()
        self.servicesListBluetooth.setReadOnly(True)
        layout.addWidget(self.servicesListBluetooth)

        # Initially disable the connect button
        self.connectButtonBluetooth.setEnabled(False)
        self.disconnectButtonBarcode.setEnabled(False)

    def initSerialBarcodeTab(self):
        layout = QVBoxLayout(self.serialBarcodeTab)

        self.labelSerial = QLabel("Seri Port Bağlantısı (Serial Barkod):")
        layout.addWidget(self.labelSerial)
        serialConnectLayout = QHBoxLayout()
        self.connectButtonSerial = QPushButton("Bağlantıyı Başlat")
        self.connectButtonSerial.clicked.connect(self.connectToSerial)
        serialConnectLayout.addWidget(self.connectButtonSerial)

        self.disconnectButtonSerial = QPushButton("Bağlantıyı Kapat")
        self.disconnectButtonSerial.clicked.connect(self.disconnectFromSerial)
        serialConnectLayout.addWidget(self.disconnectButtonSerial)
        layout.addLayout(serialConnectLayout)

        self.servicesLabelSerial = QLabel("Gelen Veriler (Serial Barkod):")
        layout.addWidget(self.servicesLabelSerial)

        self.servicesListSerial = QTextEdit()
        self.servicesListSerial.setReadOnly(True)
        layout.addWidget(self.servicesListSerial)

        # Initially disable the disconnect button
        self.disconnectButtonSerial.setEnabled(False)

    def startDiscoveryScale(self):
        print("Bluetooth Terazi cihaz keşfi başlatıldı")
        self.deviceListScale.clear()
        self.discoveryAgentScale.start()

    def deviceDiscoveryError(self, error):
        print(f"Cihaz keşfi hatası: {error}")

    def discoveryFinishedScale(self):
        print("Terazi cihaz keşfi tamamlandı")
        self.connectButtonScale.setEnabled(True)

    def discoveryFinishedBluetooth(self):
        print("Bluetooth Barkod cihaz keşfi tamamlandı")
        self.connectButtonBluetooth.setEnabled(True)

    def discoveryFinished(self):
        print("Cihaz keşfi tamamlandı")
        # Enable connect buttons after discovery is finished
        self.connectButtonBluetooth.setEnabled(True)
        self.connectButtonScale.setEnabled(True)

    def deviceDiscoveredScale(self, device):
        print(f"Bulunan Cihaz (Terazi): {device.name()}, Adres: {device.address().toString()}")
        item = QListWidgetItem(f"{device.name()} - {device.address().toString()}")
        item.setData(Qt.UserRole, device)
        self.deviceListScale.addItem(item)

    def deviceDiscoveredBluetooth(self, device):
        print(f"Bulunan Cihaz (Bluetooth Barkod): {device.name()}, Adres: {device.address().toString()}")
        item = QListWidgetItem(f"{device.name()} - {device.address().toString()}")
        item.setData(Qt.UserRole, device)
        self.deviceListBluetooth.addItem(item)

    def deviceDiscovered(self, device):
        print(f"Bulunan Cihaz: {device.name()}, Adres: {device.address().toString()}")

        if self.tabWidget.currentIndex() == 0:  # Terazi tab index
            item = QListWidgetItem(f"{device.name()} - {device.address().toString()}")
            item.setData(Qt.UserRole, device)
            self.deviceListScale.addItem(item)

        elif self.tabWidget.currentIndex() == 1:  # Bluetooth Barkod tab index
            item = QListWidgetItem(f"{device.name()} - {device.address().toString()}")
            item.setData(Qt.UserRole, device)
            self.deviceListBluetooth.addItem(item)

    def connectToDeviceScale(self):
        selectedItems = self.deviceListScale.selectedItems()
        if not selectedItems:
            QMessageBox.critical(self, "Bağlantı Hatası", "Lütfen bir cihaz seçin.")
            return

        selectedItem = selectedItems[0]
        self.selectedDeviceInfoScale = selectedItem.data(Qt.UserRole)
        print(
            f"Seçilen Cihaz (Bluetooth Terazi): {self.selectedDeviceInfoScale.name()}, Adres: {self.selectedDeviceInfoScale.address().toString()}")

        if self.socketScale and self.socketScale.state() == QBluetoothSocket.ConnectedState:
            self.socketScale.disconnectFromService()
            self.socketScale = None

        self.socketScale = QBluetoothSocket(QBluetoothServiceInfo.RfcommProtocol)
        self.socketScale.connected.connect(self.scaleConnected)
        self.socketScale.error.connect(self.socketError)
        self.socketScale.readyRead.connect(self.readFromBluetoothScale)

        try:
            self.socketScale.connectToService(self.selectedDeviceInfoScale.address(),
                                              QBluetoothUuid(QBluetoothUuid.SerialPort))
            print("Bluetooth Terazi cihazına bağlanma isteği gönderildi")
        except ConnectionError as e:
            print(f"Bağlantı hatası: {e}")
            QMessageBox.critical(self, "Bağlantı Hatası", f"Bağlantı hatası: {e}")
            return
        except Exception as e:
            print(f"Beklenmeyen hata: {e}")
            return

    def startDiscoveryBluetooth(self):
        print("Bluetooth Barkod cihaz keşfi başlatıldı")
        self.deviceListBluetooth.clear()
        self.discoveryAgentBluetooth.start()

    def connectToDeviceBluetooth(self):
        selectedItems = self.deviceListBluetooth.selectedItems()
        if not selectedItems:
            QMessageBox.critical(self, "Bağlantı Hatası", "Lütfen bir cihaz seçin.")
            return

        selectedItem = selectedItems[0]
        self.selectedDeviceInfoBluetooth = selectedItem.data(Qt.UserRole)
        print(
            f"Seçilen Cihaz (Bluetooth Barkod): {self.selectedDeviceInfoBluetooth.name()}, Adres: {self.selectedDeviceInfoBluetooth.address().toString()}")

        if self.socketBluetooth and self.socketBluetooth.state() == QBluetoothSocket.ConnectedState:
            self.socketBluetooth.disconnectFromService()
            self.socketBluetooth = None

        self.socketBluetooth = QBluetoothSocket(QBluetoothServiceInfo.RfcommProtocol)
        self.socketBluetooth.connected.connect(self.barcodeConneced)
        self.socketBluetooth.error.connect(self.socketError)
        self.socketBluetooth.readyRead.connect(self.readFromBluetoothBarcode)

        try:
            self.socketBluetooth.connectToService(self.selectedDeviceInfoBluetooth.address(),
                                                  QBluetoothUuid(QBluetoothUuid.SerialPort))
            print("Bluetooth Barkod cihazına bağlanma isteği gönderildi")
        except ConnectionError as e:
            print(f"Bağlantı hatası: {e}")
            QMessageBox.critical(self, "Bağlantı Hatası", f"Bağlantı hatası: {e}")
            return
        except Exception as e:
            print(f"Beklenmeyen hata: {e}")
            return

    def readFromBluetoothBarcode(self):
        if not self.socketBluetooth:
            return

        while self.socketBluetooth.canReadLine():
            line = self.socketBluetooth.readLine().data().decode('utf-8').strip()
            if self.validate_barcode_data(line):
                print(f"Valid barcode data: {line}")
                self.servicesListBluetooth.append(f"Barkod: {line}")
                self.trigger_camera_capture(line)  # Trigger camera capture

                # Update the startup tab with barcode, weight, and image path
                if self.latest_weight:
                    weight_status = self.latest_weight.split('-')[0].strip()
                    weight_value = self.latest_weight.split('-')[1].strip()
                    self.updateStartupTab(line, f"{weight_status} - {weight_value}", self.photo_path_value.text())
                else:
                    self.updateStartupTab(line, None, self.photo_path_value.text())
            else:
                print(f"Invalid barcode data: {line}")
                self.servicesListBluetooth.append(f"Geçersiz barkod: {line}")

    def updateStartupTab(self, barcode_data, weight, photo_path):
        """
        Update the startup tab with the latest barcode, weight, and photo path.
        """
        # Update the barcode label
        self.barcode_label.setText(f"BARKOD: {barcode_data}")

        # Update the weight label
        if weight:
            try:
                # Display weight information
                self.no_weight_device_label.setText(f"{barcode_data} - {weight}")
            except ValueError:
                print(f"Invalid weight format: {weight}")
                self.no_weight_device_label.setText(f"{barcode_data} - Verilen bilgiler eksik")
        else:
            self.no_weight_device_label.setText(f"{barcode_data} - Verilen bilgiler eksik")

        # Update the photo path label
        if photo_path:
            self.photo_path_value.setText(photo_path)
        else:
            self.photo_path_value.setText("Resim yolu yok")

        # Check if barcode and photo_path are valid
        if barcode_data and photo_path and not self.data_inserted:
            # Attempt to insert data
            if self.db_manager.insert_data(barcode_data, weight, photo_path):
                self.show_success_message("Veri başarıyla kaydedildi")
                self.data_inserted = True  # Set flag to prevent repeated insertions
            else:
                print("Data insertion failed")
        else:
            print(f"Data not inserted: barcode or photo_path is invalid or empty")



    def readFromBluetoothScale(self):
        if not self.socketScale:
            return

        while self.socketScale.canReadLine():
            line = self.socketScale.readLine().data().decode('utf-8').strip()
            print(f"Bluetooth Terazi'den gelen veri: {line}")

            # Emit the signal with the new data
            self.newDataAvailable.emit(line)

    newDataAvailable = pyqtSignal(str)

    @pyqtSlot(str)
    def updateUI(self, line):
        if self.devmode:
            # Insert original data to the top of the original data list
            self.originalDataListScale.insertItem(0, line)

        if self.selected_model_regex:
            match = self.selected_model_regex.search(line)
            if match:
                # Extract the weight value using regex
                weight = match.group(1).strip()
                self.servicesListScale.append(f"Terazi: {line}")
                self.latest_weight = weight  # Update the latest weight
                self.updateStartupTab(
                    self.barcode_label.text().split(': ')[1].strip(),
                    self.latest_weight,
                    self.photo_path_value.text()
                )

                if self.devmode:
                    # Insert captured data to the top of the captured data list
                    self.capturedDataListScale.insertItem(0, f"{weight} kg")

            else:
                print(f"Geçersiz veri: {line}")
                self.servicesListScale.append(f"Geçersiz veri: {line}")
        else:
            print("No regex pattern set for model")

    def connectToSerial(self):
        port = self.serial_port
        if not port:
            QMessageBox.critical(self, "Bağlantı Hatası", "Lütfen bir seri port girin.")
            return

        self.serialListener = SerialListener(port)
        self.serialListener.barcode_received.connect(self.handleSerialBarcodeData)
        self.serialListener.start()

        self.serialPort = port
        self.servicesListSerial.append(f"Bağlantı başlatıldı: {port}")
        self.tabWidget.setTabEnabled(2, False)
        self.no_barcode_device_label.clear()
        self.connectButtonSerial.setEnabled(False)
        self.disconnectButtonSerial.setEnabled(True)

    def handleSerialBarcodeData(self, data):
        if self.validate_barcode_data(data):
            print(f"Valid barcode data: {data}")
            self.servicesListSerial.append(f"Barkod: {data}")
            self.trigger_camera_capture(data)  # Trigger camera capture

            # Update the startup tab barcode label
            self.barcode_label.setText(f"BARKOD: {data}")
        else:
            print(f"Invalid barcode data: {data}")
            self.servicesListSerial.append(f"Geçersiz barkod: {data}")

    def disconnectFromDeviceScale(self):
        if self.socketScale:
            self.socketScale.disconnectFromService()
            self.socketScale.close()
            self.socketScale = None
            print("Terazi cihazı bağlantısı kesildi")
            self.connectButtonScale.setEnabled(True)
            self.disconnectButtonScale.setEnabled(False)
            self.no_weight_device_label.setText("Bağlı Cihaz Yok")

    def disconnectFromDeviceBarcode(self):
        if self.socketBluetooth:
            self.socketBluetooth.disconnectFromService()
            self.socketBluetooth.close()
            self.socketBluetooth = None
            print("Barkod Okuyucu cihazı bağlantısı kesildi")
            self.connectButtonBluetooth.setEnabled(True)
            self.disconnectButtonBarcode.setEnabled(False)
            self.tabWidget.setTabEnabled(3, True)
            self.no_barcode_device_label.setText("Bağlı Cihaz Yok")

    def disconnectFromSerial(self):
        if self.serialListener:
            self.serialListener.stop()
            self.serialListener.wait()
            self.serialListener = None
            self.servicesListSerial.append(f"Bağlantı kapatıldı: {self.serialPort}")
            self.tabWidget.setTabEnabled(2, True)
            self.no_barcode_device_label.setText("Bağlı Cihaz Yok")
            self.connectButtonSerial.setEnabled(True)
            self.disconnectButtonSerial.setEnabled(False)

    def connected(self):
        print("Cihaza başarıyla bağlanıldı")

    def scaleConnected(self):
        try:
            print("Cihaza başarıyla bağlanıldı")
            self.no_weight_device_label.clear()
            self.disconnectButtonScale.setEnabled(True)
            self.tabWidget.setTabEnabled(2, True)  # Bluetooth Barkod tab
            self.tabWidget.setTabEnabled(3, True)  # Serial Barkod tab

            # Show model selection dialog
            self.showModelSelectionDialog()
        except Exception as e:
            print(f"Error in scaleConnected: {e}")
            # Optionally, display a message box or handle the error appropriately

    def barcodeConneced(self):
        print("Cihaza başarıyla bağlanıldı")
        self.no_barcode_device_label.clear()
        self.disconnectButtonBarcode.setEnabled(True)
        self.tabWidget.setTabEnabled(3, False)

    def socketError(self, error):
        error_message = f"Soket hatası: {error}"
        print(error_message)  # Terminale yazdır

        # Arayüze yazdır
        QMessageBox.critical(self, "Soket Hatası", error_message)

    def validate_barcode_data(self, barcode_data):
        if len(barcode_data) != 13:
            return False
        for char in barcode_data:
            if not char.isdigit() or not 0 <= int(char) <= 9:
                return False
        return True

    def trigger_camera_capture(self, barcode_data):
        print(f"Kamera tetiklendi: Barkod - {barcode_data}")
        rtsp_url = f'rtsp://{self.camera_user}:{self.camera_password}@{self.camera_ip}:554/stream'
        cap = cv2.VideoCapture(rtsp_url)

        filename = None
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                directory = "captured_images"
                if not os.path.exists(directory):
                    os.makedirs(directory)

                filename = os.path.join(directory, f"{barcode_data}_{timestamp}.jpg")
                cv2.imwrite(filename, frame)
                print(f"Fotoğraf kaydedildi: {filename}")
                self.servicesListSerial.append(f"Fotoğraf kaydedildi: {filename}")
            else:
                print("Kamera görüntüsü alınamadı")
                self.servicesListSerial.append("Kamera görüntüsü alınamadı")
        else:
            print("Kamera açılamadı")
            self.servicesListSerial.append("Kamera açılamadı")

        cap.release()

        # Update the startup tab photo path label
        if filename:
            self.photo_path_value.setText(filename)
        else:
            self.photo_path_value.setText("Resim yolu yok")

    def closeEvent(self, event):
        """
        Override the closeEvent to clean up connections and threads.
        """
        # Stop the Bluetooth connections
        if self.socketScale and self.socketScale.state() == QBluetoothSocket.ConnectedState:
            self.socketScale.disconnectFromService()
        if self.socketBluetooth and self.socketBluetooth.state() == QBluetoothSocket.ConnectedState:
            self.socketBluetooth.disconnectFromService()

        # Stop the serial listener if it exists
        if self.serialListener:
            self.serialListener.stop()

        # Close the database connection
        if self.db_manager:
            self.db_manager.close()

        # Call the base class implementation
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = BluetoothManager()
    window.show()
    sys.exit(app.exec_())
