## Data Collector

This Project aims to collect data for object detection and image classification problems from market registers.
Project collects barcode, weight and image path of the given product.

1. **Requirements**: 
   - Python 3.12
   - serial
   - pynput
   - opencv
   - sqlite3
   - PyQt5
   - configparser
   - pyinstaller

## Hardware Requirements:

- Ip camera supports rtsp protocol
- Classic Bluetooth Connection Supported Scale
- Com port listener barcode scanner

**Configure**:
 ```bash
     pyinstaller --onefile scrolldownissue.py
 ```

after bulding exe file create a folder and paste it there

1. Create 'config.ini' file(if you run the exe without creating, it will automatically creates and shuts down)

2.  Config.ini file

Config.ini file have 4 sections can be accessed with configparser library: [Camera], [SerialPort], [models], ve [devmode].

### [Camera] Section

- **ip_address**: 192.188.1.1 #example
- **username**: admin
- **password**: admin123

### [SerialPort] Section

-**port**: COM4 #example

### [Models] Section

-**ScaleModel1**: /S\s{1,}([0-9.\s]+?)kg$/gm #example

-**ScaleModel2**: (\d+(.\d+)?)\s?kg #example

add more regexes for your models

### [devmode] Section
-**on**: 1 or 0 
opens devmode

3. After configuring the file start the exe program
4. Scan the Scales in Terazi section
5. Connect to selected device via classical bluetooth connection (pre-pairing maybe needed)
6. Connect your barcode scanner via usb (bluetooth barcode scanner not tested suggesting serial connection)
7. After everything done scan your first barcode.

## Outputs
- under captured_images folder .jpg file of the product
- in product_data.db (barcode, weight, image_path)

**Database**:
```
(1, '8690793020082', '0.156', 'captured_images\\8690793020082_20240724-100833.jpg')
(2, '8690793020082', '0.450', 'captured_images\\8690793020082_20240724-100842.jpg')
```

