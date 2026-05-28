# 板子和iPhone UWB 

## UWB 连接建立流程
UWB 建立连接是需要接触[BLE](https://en.wikipedia.org/wiki/Bluetooth_Low_Energy).

### BLE 连接建立
背景知识：
    蓝牙连接涉及角色的概念：
    Central                             扫描周围设备，并发起连接
    Peripheral（外设）                   广播自己蓝牙信息

uwb中，此时我们将板子当作Perpheral 角色，iPhone当作Central，可以使用XCode打开iOS 文件夹中Qorvo_Nearby_Interaction_v1.3.5，没解压之前需要先解压下。设置好包名和app 签名后，运行手机程序，建议使用iPhone11及以上型号的手机，iPhone11之前的手机对UWB基本不支持。

对于外设端：注册广播服务：
```
    # 注册广播
    ad_manager = dbus.Interface(bus.get_object(SERVICE_NAME, ADAPTER_PATH),
                                "org.bluez.LEAdvertisingManager1")
    advert = Advertisement(bus, 0, "peripheral")
    ad_manager.RegisterAdvertisement(advert.get_path(), {},
                                     reply_handler=lambda: print("📡 Advertising started"),
                                     error_handler=lambda e: print("❌ Advertising error:", e))
```
此时在iPhone手机的BLE 设备列表中，就会发现多了个刚刚广播的设备。

点击Connect 之后，此时会没有啥反应，因为Peripheral，还没设置连接响应逻辑。
这里面：
RX Characteristics：Peripheral 用于接受Centeral发送数据channel id
TX Characteristics：Peripheral向Central 发送数据channel id，Centeral 在连接后需要根据广播出去Characteristics信息，订阅这个channel。
Central 和 Peripheral 连接并相互设置会话频道后，就可以开始交互数据了。

 Peripheral | ===Advertisement==>  | Central 

            |                      |
            | <------req connect-- |
            |                      |
            | ---RX/TX Charact---->|
            |                      |
            | ---Subscribe RX ---->|
            |                      |
            | <--Subscribe TX -----|
            |                      |
            |<----Send 0x0a -------|
            |                      |
            |---Send 0x01...------>| 
            |                      |
            |<---Send 0x0b---------|
            |                      |
            |----Send 0x02-------->|
            |                      |
            |        ....          |

 0x01 0x02 等表示message Id，每个ID对应的语义如下表所示：
 
```
enum MessageId: UInt8 {
    // Messages from the accessory.
    case accessoryConfigurationData = 0x1
    case accessoryUwbDidStart = 0x2
    case accessoryUwbDidStop = 0x3
    
    // Messages to the accessory.
    case initialize = 0xA
    case configureAndStart = 0xB
    case stop = 0xC
    
    // User defined/notification messages
    case getReserved = 0x20
    case setReserved = 0x21

    case iOSNotify = 0x2F
}
```
到此 整个连接UWB连接流程建立。
然后就可以进行测距，并通过BLE 进行测距数据传输了。


## linux  环境配置
pip3 install --user colcon-common-extensions
echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
apt install -y cmake build-essential
pip3 uninstall -y em empy
sudo apt install -y python3-empy
sudo apt install -y python3 python3-dev
mkdir -p /sysroot/usr/lib/aarch64-linux-gnu
mkdir -p /sysroot/usr/include
ln -sf /usr/lib/aarch64-linux-gnu/libpython3.10.so \
       /sysroot/usr/lib/aarch64-linux-gnu/libpython3.10.so

ln -sfn /usr/include/python3.10 \
        /sysroot/usr/include/python3.10
python3 -m pip install pyserial