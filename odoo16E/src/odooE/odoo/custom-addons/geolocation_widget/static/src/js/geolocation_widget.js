/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useInputField } from "@web/views/fields/input_field_hook";
const { Component, useRef, onMounted } = owl;

// ✅ 确保 Google Maps API 只加载一次
let googleMapsLoaded = false;

export class GeoLocationField extends Component {
    static template = 'GeoLocationField';

    setup() {
        super.setup();
        this.inputRef = useRef('geoInput');       // 经纬度输入框
        this.mapContainer = useRef('mapContainer'); // 地图容器
        this.updateButton = useRef('updateButton'); // 按钮：加载地图
        this.addressInput = useRef('addressInput'); // 地址输入框
        this.searchAddressButton = useRef('searchAddressButton'); // 按钮：查询地址
        this.marker = null;  // 地图标记

        onMounted(() => {
            this.updateButton.el.addEventListener('click', () => this._loadAndInitMap());
            this.searchAddressButton.el.addEventListener('click', () => this._searchAddress());
        });
    }

    async _loadAndInitMap() {
        try {
            // 显示地图容器
            this.mapContainer.el.style.display = "block";

            // ✅ 确保 Google Maps API 只加载一次
            if (!googleMapsLoaded) {
                await this._loadGoogleMapsAPI();
            }

            // ✅ 确保 `mapContainer` 存在后初始化地图
            this._initializeMap();
        } catch (error) {
            console.error("❌ 加载 Google 地图失败:", error);
        }
    }

    async _loadGoogleMapsAPI() {
        return new Promise((resolve, reject) => {
            if (googleMapsLoaded) {
                console.log("✅ Google Maps API 已加载");
                resolve();
                return;
            }

            console.log("🔄 正在加载 Google Maps API...");
            const script = document.createElement("script");
            script.src = `https://maps.googleapis.com/maps/api/js?key=AIzaSyAaRtvYPCxY0Ewi6oCyg16AdSlr74rx0q4&libraries=places`;
            script.defer = true;
            script.async = true;
            script.onload = () => {
                googleMapsLoaded = true; // ✅ 标记 API 已加载
                console.log("✅ Google Maps API 载入完成！");
                resolve();
            };
            script.onerror = (err) => {
                console.error("❌ Google Maps API 加载失败:", err);
                reject(err);
            };
            document.head.appendChild(script);
        });
    }

    _initializeMap() {
        if (!this.mapContainer.el) {
            console.error("❌ `mapContainer` 仍然为空，地图初始化失败！");
            return;
        }

        console.log("✅ 初始化 Google 地图...");
        this.map = new google.maps.Map(this.mapContainer.el, {
            center: { lat: 25.032969, lng: 121.565418 }, // 默认台北101
            zoom: 12,
        });

        // 监听地图点击事件
        this.map.addListener("click", (event) => {
            this._setLocation(event.latLng);
        });
    }

    _setLocation(latLng) {
        const latitude = latLng.lat();
        const longitude = latLng.lng();
        this.inputRef.el.value = `${latitude},${longitude}`;
        this.props.update(this.inputRef.el.value);
        console.log("📌 选中坐标:", latitude, longitude);

        // 在地图上放置标记
        if (this.marker) {
            this.marker.setMap(null);
        }
        this.marker = new google.maps.Marker({
            position: { lat: latitude, lng: longitude },
            map: this.map,
            title: "Selected Location",
        });

        // 移动地图视角
        this.map.setCenter({ lat: latitude, lng: longitude });
    }

    async _searchAddress() {
        const address = this.addressInput.el.value.trim();
		console.log(address);
        if (!address) {
            alert("请输入地址进行搜索！");
            return;
        }

        try {
            const geocoder = new google.maps.Geocoder();
            geocoder.geocode({ address }, (results, status) => {
                if (status === "OK" && results[0]) {
                    const location = results[0].geometry.location;
                    console.log("📍 地址解析成功:", location.lat(), location.lng());

                    // 在地图上放置标记
                    this._setLocation(location);
                } else {
                    console.error("❌ 地址解析失败:", status);
                    alert("地址解析失败，请检查输入的地址！");
                }
            });
        } catch (error) {
            console.error("❌ 地址解析异常:", error);
        }
    }
}

// ✅ **注册到 Odoo**
GeoLocationField.components = { useRef };
registry.category("fields").add("geo_location", GeoLocationField);
