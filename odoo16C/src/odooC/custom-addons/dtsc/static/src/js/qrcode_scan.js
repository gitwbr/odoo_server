/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller"; // 引入 FormController
import rpc from 'web.rpc'; // 引入 RPC 模块

// 使用 patch 直接扩展 FormController
console.log("Your dtsc FormController is loading...");
patch(FormController.prototype, 'dtsc.FormController', {
	setup() {
		this._super();
		console.log("setup 被调用");

		let attempts = 0; // 尝试次数
		const maxAttempts = 10; // 最大尝试次数

		const intervalId = setInterval(() => {
			const button_lb = document.getElementById('scan_qr_button_lb'); // 冷裱
			const button_gb = document.getElementById('scan_qr_button_gb'); // 过板
			const button_cq = document.getElementById('scan_qr_button_cq'); // 裁切
			const button_hz = document.getElementById('scan_qr_button_hz'); // 後製
			const button_pg = document.getElementById('scan_qr_button_pg'); // 品管
			const button_dch = document.getElementById('scan_qr_button_dch'); // 待出货
			const button_ych = document.getElementById('scan_qr_button_ych'); // 已出货
			const closebutton = document.getElementById('close_qr_modal_btn'); // 查找按钮
			
			if (button_ych) {
				console.log("按钮已经找到: #scan_qr_button"); 
				const recordId = this.model.root.data.id;
				let page = "none";
				if(this.model.root.data.is_open_makeout_qrcode)
				{
					console.log("此页面为makeout")
					page = "makeout"
				}
				else if(this.model.root.data.is_open_makein_qrcode)
				{
					console.log("此页面为makein")
					page = "makein"
				}
				console.log(recordId)
				if(button_lb)
					button_lb.addEventListener('click', () => this.startQRScanner('lb',recordId,page)); // 绑定点击事件
				if(button_gb)
					button_gb.addEventListener('click', () => this.startQRScanner('gb',recordId,page)); // 绑定点击事件
				if(button_cq)
					button_cq.addEventListener('click', () => this.startQRScanner('cq',recordId,page)); // 绑定点击事件
				if(button_hz)
					button_hz.addEventListener('click', () => this.startQRScanner('hz',recordId,page)); // 绑定点击事件
				if(button_pg)
					button_pg.addEventListener('click', () => this.startQRScanner('pg',recordId,page)); // 绑定点击事件
				if(button_dch)
					button_dch.addEventListener('click', () => this.startQRScanner('dch',recordId,page)); // 绑定点击事件
				if(button_ych)
					button_ych.addEventListener('click', () => this.startQRScanner('ych',recordId,page)); // 绑定点击事件
				clearInterval(intervalId); // 找到按钮后清除定时器
				if(closebutton)
					closebutton.addEventListener('click', () => this.closeQRScanner());
			} else {
				attempts++;
				console.log("按钮未找到: #scan_qr_button");
				if (attempts >= maxAttempts) {
					console.log("达到最大尝试次数，退出。");
					clearInterval(intervalId); // 达到最大尝试次数后清除定时器
				}
			}
		}, 1000); // 每秒检查一次
	},
	// console.log("222222222222222222222");
	closeQRScanner:function(){
		// const qrReaderElement = document.getElementById("qr-reader"); // 获取用于显示摄像头的元素
		const qrReaderElement = document.getElementById("qr-modal"); // 获取用于显示摄像头的元素
        
        if (!qrReaderElement) {
            console.error("找不到 ID 为 qr-reader 的元素");
            return;
        }
		if (this.html5QrCode) {
            this.html5QrCode.stop().then(() => {
                console.log("摄像头已关闭");
                qrReaderElement.style.display = "none"; // 隐藏 QR 码读取器
                this.html5QrCode = null; // 清除实例
            }).catch(err => {
                console.error("停止扫描时出错:", err);
            });
        } else {
            // 如果没有实例，直接隐藏
            qrReaderElement.style.display = "none"; 
        }
	},

    startQRScanner: function (buttonType,makeinId,page) {
        // 创建 Html5Qrcode 实例并启动扫描
		// const qrReaderElement = document.getElementById("qr-reader"); // 获取用于显示摄像头的元素
		const qrReaderElement = document.getElementById("qr-modal"); // 获取用于显示摄像头的元素
        
        if (!qrReaderElement) {
            console.error("找不到 ID 为 qr-reader 的元素");
            return;
        }

        // 显示 QR 码读取器
        // qrReaderElement.style.display = "block"; 
        qrReaderElement.style.display = "flex"; 
        const html5QrCode = new Html5Qrcode("qr-reader");
		
		const closebutton = document.getElementById('close_qr_modal_btn'); 
		closebutton.disabled = false
		// qrReaderElement.style.display = "block"; 
        // 启动二维码扫描
        html5QrCode.start(
            { facingMode: "environment" },
            {
                fps: 10,
                qrbox: 250
            },
            (decodedText) => {
                console.log("扫描到的二维码:", decodedText);
                this.callPythonMethod(decodedText,buttonType,makeinId,page); // 调用 Python 方法
                html5QrCode.stop(); // 停止扫描
				qrReaderElement.style.display = "none"; 
            },
            (errorMessage) => {
                console.warn(`QR code scan error: ${errorMessage}`);
            }
        ).catch(err => {
            console.error("Unable to start scanning: ", err);
        });
    },

    callPythonMethod: function (qrCodeData,buttonType,makeinId,page) {
        // 调用后端 Python 方法
		console.log("二维码:", qrCodeData);
		// const decodedString = atob(qrCodeData); // 使用 atob() 解码 Base64 编码的字符串
		// console.log("解码后的字符串:", decodedString);
		
		if (!makeinId) {
			alert("未找到關鍵參數請刷新重試！");
			// console.error("Makein ID 不存在。无法继续操作。");
			return;
		}
		
		console.log("方法:", buttonType);
		let type;
		if (buttonType === "lb")
			type = '冷裱';
		else if(buttonType === "gb")
			type = '過板';
		else if(buttonType === "cq")
			type = '裁切';
		else if(buttonType === "hz")
			type = '後製';
		else if(buttonType === "pg")
			type = '品管';
		else if(buttonType === "dch")
			type = '待出貨';
		else if(buttonType === "ych")
			type = '已出貨';
		else
			type = "0";
		console.log("方法:", type)
		console.log("id:", makeinId)
		if (type === "0")
		{
			alert("qrcode格式不正確，請檢查！")
			return
		}
		
		// const isConfirmed = confirm(`是否確認此員工 ${qrCodeData}，在所勾選的 ${type} 中簽名？`); 

		// if (isConfirmed) {
		if(page == "makein")
		{
			rpc.query({
				model: 'dtsc.makein',  // 替换为你的模型
				method: 'check_name',  // 替换为你的方法名
				args: [[],[qrCodeData,buttonType,makeinId]],  // 传递扫描到的二维码数据
			}).then(result => {
				// alert(result.employeename)
				if(result.success)
				{
					let workname = result.employeename
					const isConfirmed_make_in = confirm(`是否確認此員工 ${workname}，在所勾選的 ${type} 中簽名？`); 
					// const isConfirmed_make_in = confirm(`是否確認此員工 ${result.employeename}，在所勾選的 ${type} 中簽名？`); 
					
					if (isConfirmed_make_in) {
						rpc.query({
						model: 'dtsc.makein',  // 替换为你的模型
						method: 'process_qr_code',  // 替换为你的方法名
						args: [[],[result.employeename,buttonType,makeinId]],  // 传递扫描到的二维码数据
						}).then(result => {
							window.location.reload();
							console.log("Python 方法返回的结果:", result);
							// 可选：根据需要处理返回结果
						}).catch(error => {
							window.location.reload();
							console.error("调用 Python 方法出错:", error);
						});
					}
				}
				else
				{
					alert("無法找到該員工！請確認Qrcode正確！")
				}
				console.log("Python 方法返回的结果:", result);
			}).catch(error => {
				alert("錯誤！")
				console.error("调用 Python 方法出错:", error);
			});
			
			
		}
		else if(page == "makeout")
		{
			rpc.query({
				model: 'dtsc.makein',  // 替换为你的模型
				method: 'check_name',  // 替换为你的方法名
				args: [[],[qrCodeData,buttonType,makeinId]],  // 传递扫描到的二维码数据
			}).then(result => {
				// alert(result.employeename)
				if(result.success)
				{
					let workname = result.employeename
					const isConfirmed_make_out = confirm(`是否確認此員工 ${workname}，在所勾選的 ${type} 中簽名？`); 
					
					if (isConfirmed_make_out) {
						rpc.query({
							model: 'dtsc.makeout',  // 替换为你的模型
							method: 'process_qr_code',  // 替换为你的方法名 
							args: [[],[workname,buttonType,makeinId]],  // 传递扫描到的二维码数据
						}).then(result => {
							window.location.reload();
							console.log("Python 方法返回的结果:", result);
							// 可选：根据需要处理返回结果
						}).catch(error => {
							window.location.reload();
							console.error("调用 Python 方法出错:", error);
						});
					}
				}
				else
				{
					alert("無法找到該員工！請確認Qrcode正確！")
				}
				console.log("Python 方法返回的结果:", result);
			}).catch(error => {
				alert("錯誤！")
				console.error("调用 Python 方法出错:", error);
			});
			
			
		}
			
		// }
		
    },
});