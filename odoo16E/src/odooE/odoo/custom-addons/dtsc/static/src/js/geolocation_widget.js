/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useInputField } from "@web/views/fields/input_field_hook";
const { Component, useRef, onMounted } = owl;

let googleMapsLoaded = false;
export class GeoLocationField extends Component {
    static template = 'GeoLocationField';

    setup() {
        super.setup();
        this.inputRef = useRef('geoInput');
        this.addressInput = useRef('addressInput');  // 地址输入框
        this.mapContainer = useRef('mapContainer'); // 地图容器
        this.updateButton = useRef('updateButton'); // 获取坐标按钮
        this.searchAddressButton = useRef('searchAddressButton'); // 搜索地址按钮
        this.toggleMapButton = useRef('toggleMapButton'); // 显示/隐藏地图按钮
        this.mapVisible = false;  // 记录地图是否可见
        this.map = null;
        this.marker = null; // 标记点
        this.geocoder = null; // 用于地址解析

        onMounted(() => {
			if (this.props.value) {
				this.inputRef.el.value = this.props.value;
			}
            this.updateButton.el.addEventListener("click", this._loadAndInitMap.bind(this));
            this.searchAddressButton.el.addEventListener("click", this._searchAddress.bind(this));
            this.toggleMapButton.el.addEventListener("click", this._toggleMap.bind(this));
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
            if (window.google && window.google.maps) {
                console.log("✅ Google Maps API 已加载");
                resolve();
                return;
            }
            const script = document.createElement('script');
            script.src = `https://maps.googleapis.com/maps/api/js?key=AIzaSyAaRtvYPCxY0Ewi6oCyg16AdSlr74rx0q4&libraries=places`;
            script.defer = true;
            script.async = true;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    async _initializeMap() {
        if (!this.mapContainer.el) {
            console.error("❌ Error: mapContainer is null, cannot initialize map.");
            return;
        }        
        console.log("✅ 初始化地图");
		let defaultLocation = { lat: 25.032969, lng: 121.565418 }; 
		if (this.props.value) {
            const coords = this.props.value.split(",");
            if (coords.length === 2) {
                const lat = parseFloat(coords[0]);
                const lng = parseFloat(coords[1]);
                if (!isNaN(lat) && !isNaN(lng)) {
                    defaultLocation = { lat, lng };
                }
            }
        }
		
        this.map = new google.maps.Map(this.mapContainer.el, {
            center: defaultLocation, // 默认台北101
            zoom: 16,
        });

        this.geocoder = new google.maps.Geocoder();
		if (this.props.value) {
            this.marker = new google.maps.Marker({
                position: defaultLocation,
                map: this.map,
                title: "Saved Location",
            });
        }
        this.map.addListener("click", (event) => {
            this._setLocation(event.latLng);
        });
    }

    _setLocation(latLng) {
        const latitude = latLng.lat();
        const longitude = latLng.lng();
        this.inputRef.el.value = `${latitude},${longitude}`;
        this.props.update(this.inputRef.el.value);

        // 添加或移动标记
        if (this.marker) {
            this.marker.setPosition(latLng);
        } else {
            this.marker = new google.maps.Marker({
                position: latLng,
                map: this.map,
                title: "Selected Location",
            });
        }
    }

    async _getCurrentLocation() {
        try {
            const position = await this._getCurrentPosition();
            const { latitude, longitude } = position.coords;
            this._setLocation(new google.maps.LatLng(latitude, longitude));
        } catch (error) {
            console.error('❌ 获取当前位置失败:', error);
        }
    }

    _getCurrentPosition() {
        return new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
                position => resolve(position),
                error => reject(error)
            );
        });
    }

    _searchAddress() {
        const address = this.addressInput.el.value;
        if (!address) {
            alert("请输入地址！");
            return;
        }

        this.geocoder.geocode({ address: address }, (results, status) => {
            if (status === "OK") {
                const location = results[0].geometry.location;
                this.map.setCenter(location);
                this._setLocation(location);
            } else {
                console.error("❌ 地址查询失败:", status);
                alert("地址查询失败: " + status);
            }
        });
    }

    _toggleMap() {
        // if (!this.map) {
            // this._initializeMap();
        // }

        // this.mapVisible = !this.mapVisible;
        this.mapContainer.el.style.display = "none";
    }
}

GeoLocationField.components = { useRef };
registry.category("fields").add("geo_location", GeoLocationField);
