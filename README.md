# MEIZU Remoter Gateway

# 魅族遥控器蓝牙网关集成
[魅族遥控器蓝牙网关](https://github.com/georgezhao2010/esp32_meizu_remoter_gateway)的Home Assistant集成组件

# 特点
- 网关设备自动发现，Home Assistant中点击鼠标两次即可完成集成添加配置
- 支持手工添加集成，输入网关IP地址即可完成集成添加配置
- 网关绑定的遥控器自动发现，并支持在集成中解除绑定
- 通过服务支持红外发射

# 下载安装
使用HACS自定义存储库安装，或者从[Latest Release](https://github.com/georgezhao2010/meizu_remoter_gateway/releases/latest)下载最新的Release，并将其中的`custom_components/meizu_remoter_gateway`目录放置到你的Home Assistant的`custom_components`目录下。

# 配置
## 自动配置
魅族遥控器蓝牙网关集成支持Home Assistant的自动发现，网关一经上电，就会自动出现在Home Assistant的集成界面，如图所示：

![auto-discover](https://user-images.githubusercontent.com/27534713/131560205-e2f3022c-c65d-4752-a219-f8c8cd83827f.png)

点击配置按钮，再确定添加即可完成配置。

![auto-config](https://user-images.githubusercontent.com/27534713/131560709-27730d18-d7a8-41c3-a82b-79cc6da6811e.png)

如果你的Home Assistant没有自动发现网关设备，可以尝试给网关设备重新上电一次。如果仍不能自动发现，可以尝试手动配置。

## 手动配置
在Home Assistant的集成界面，添加集成并搜索"MEIZU Remoter Gateway"，并添加集成。手动配置需要输入网关设备的IP地址。

![manual-config](https://user-images.githubusercontent.com/27534713/131565625-c94d1e30-6895-4a1f-882e-28aa753142df.png)


***注意：无论是自动配置还是手动配置，应在路由器提前给网关设备指定分配静态IP，以免因IP地址变动造成配置失效***

***注意：网关集成对网关固件有最小版本号的要求，如果不满足，则无法自动配置，手动配置也会提示错误。关于对应的网关版本号，请参阅发行说明***

## 选项
集成的选项为网关的数据更新间隔时间，默认为5分钟，有效设置范围为1-30分钟。从节省遥控器电量考虑，设为5-10分钟比较合适，毕竟更新的温湿度数据的实时性并不强。

![update-interval](https://user-images.githubusercontent.com/27534713/131565638-c7e009e4-410d-4a1a-baf9-63649f675640.png)


# 设备与实体
刚添加完集成时，集成下应该没有设备和实体。但如果在网关绑定新的遥控器，或者下次数据更新时，遥控器设备和实体会立刻出现在集成中。

![intergration](https://user-images.githubusercontent.com/27534713/131565658-a783d095-57bf-4cf8-a7f4-5c0bfe0c68a2.png)


## 设备
遥控器设备默认名称为"MEIZU Remoter <蓝牙地址>"，可根据你的实际摆放位置改动，如"卧室温度计"等。

![device](https://user-images.githubusercontent.com/27534713/131565672-24739c3f-1aec-4907-90db-49274235b61f.png)


## 实体
遥控器设备包含4个传感器，分别见下表
| 实体ID | 默认名称 | 含义 |
| ---- | ---- | ---- |
| `sensor.<网关编号>_<蓝牙地址>_remoter` | MEIZU Remoter <蓝牙地址> | 遥控器实体，服务调用需传入此实体ID |
| `sensor.<网关编号>_<蓝牙地址>_battery` | MEIZU Remoter <蓝牙地址> Battery | 遥控器电量 |
| `sensor.<网关编号>_<蓝牙地址>_humidity` | MEIZU Remoter <蓝牙地址> Humidity | 湿度传感器数值 |
| `sensor.<网关编号>_<蓝牙地址>_temperature` | MEIZU Remoter <蓝牙地址> Temperature | 温度传感器数值 |
| `sensor.<网关编号>_<蓝牙地址>_rssi` | MEIZU Remoter <蓝牙地址> RSSI | 蓝牙信号强度 |

***注意：网关采集数据时，如果轮询某个遥控器数据失败，该遥控器下所有传感器将被标识为不可用，直到下次轮询成功。如果连续5次轮询失败，该设备将会被移除出轮询列表（并不会解除绑定关系），在下次重新启动网关之前，不再更新该设备的数据。这种情况可能是遥控器设别故障或电池耗尽，在排除故障后，将设备与网关重新绑定，可恢复数据的更新。***

# 服务
集成包含有有以下服务
## 绑定
如果需要网关启动绑定操作，调用`bind`服务，服务调用形式如下：
```
service: meizu_remoter_gateway.bind
data:
  serial_no: 1B32A9
```
serial_no参数为网关序列号

## 调整绑定信号阈值
网关进行绑定操作是以附近蓝牙设备的信号判断是否有蓝牙设备“靠近”，从而完成绑定操作，该信号默认阈值为-30dBm。

由于各人使用的硬件设备不同，在相同场景下，可能该阈值需要个性化调整，因此提供阈值调整服务，该服务调用形式如下：
```
service: meizu_remoter_gateway.bind_threshold
data:
  serial_no: 1B32A9
  threshold: -35
```
serial_no参数为网关序列号
threshold参数为设置的信号阈值(-15dBm至-60dBm，建议值-25dBm至-40dBm)

## 解除绑定
如果需要将单一遥控器从网关移除绑定，调用`remove_bind`服务，服务调用形式如下：
```
service: meizu_remoter_gateway.remove_bind
data:
  entity_id: sensor.1c4bd9_683e34ccdfad_remoter
```
在调用该服务后，如果成功，该遥控器设备及传感器会永久从Home Assistant移除。要恢复设备，重新与网关绑定即可。

## 发射红外码
可以通过遥控器发射指定的红外码，调用`send_ir`服务，服务调用形式如下：
```
service: meizu_remoter_gateway.ir_send
data:
  entity_id: sensor.1c4bd9_683e34ccdfad_remoter
  key: 65001C63C68D8000C8
  ir_code: 112220111911203a00001aa000012...
```
以上红外码用于打开/关闭SONY电视。

***红外码发射已知每个遥控器都各不相同，比如上述红外码发射命令，使用一个遥控器是可以工作的，但是另外的遥控必须使用`65001C8C1A8D800018`才可以正常开闭我的SONY电视。所以目前该功能实用性不高，有待后续改进***

# 调试
要打开调试日志输出，在configuration.yaml中做如下配置
```
logger:
  default: warn
  logs:
    custom_components.meizu_remoter_gateway: debug
```
