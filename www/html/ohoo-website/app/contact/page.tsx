"use client";

// import { useState, FormEvent } from 'react';
import Navbar from '@/components/Navbar';
import Image from 'next/image';

/* const contactMethods = [
  {
    name: '客戶服務',
    description: '我們的客服團隊隨時為您服務',
    phone: '+886 2 2345 6789',
    email: 'service@euhonerp.com',
    hours: '週一至週五 9:00-18:00'
  },
  {
    name: '技術支援',
    description: '遇到技術問題？我們來幫您',
    phone: '+886 2 2345 6790',
    email: 'support@euhonerp.com',
    hours: '24/7 全天候服務'
  },
  {
    name: '業務諮詢',
    description: '了解更多關於我們的服務',
    phone: '+886 2 2345 6791',
    email: 'sales@euhonerp.com',
    hours: '週一至週五 9:00-18:00'
  }
]; */

/* 暂时注释掉未使用的接口
interface FormData {
  name: string;
  company: string;
  email: string;
  phone: string;
  message: string;
}
*/

export default function Contact() {
  /* 暂时注释掉未使用的状态和函数
  const [formData, setFormData] = useState<FormData>({
    name: '',
    company: '',
    email: '',
    phone: '',
    message: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitStatus, setSubmitStatus] = useState<'idle' | 'success' | 'error'>('idle');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    
    try {
      // 这里添加表单提交逻辑
      // 模拟API调用
      await new Promise(resolve => setTimeout(resolve, 1000));
      setSubmitStatus('success');
    } catch {
      setSubmitStatus('error');
    } finally {
      setIsSubmitting(false);
    }
  };
  */

  return (
    <main className="flex min-h-screen flex-col">
      <Navbar />
      
      {/* Header */}
      {/* <div className="bg-white px-6 py-24 sm:py-32 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-base font-semibold leading-7 text-blue-600">聯絡我們</h2>
          <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
            讓我們一起打造您的數位化未來
          </p>
          <p className="mt-6 text-lg leading-8 text-gray-600">
            填寫以下表單，我們會盡快與您聯繫，為您提供最適合的解決方案
          </p>
        </div>
      </div> */}

      {/* Contact Form */}
      {/* <div className="bg-gray-50 px-6 py-24 sm:py-32 lg:px-8">
        <div className="mx-auto max-w-2xl">
          <form onSubmit={handleSubmit} className="space-y-8">
            <div className="grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2">
              <div>
                <label htmlFor="name" className="block text-sm font-semibold leading-6 text-gray-900">
                  姓名
                </label>
                <div className="mt-2.5">
                  <input
                    type="text"
                    name="name"
                    id="name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    autoComplete="given-name"
                    required
                    className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="company" className="block text-sm font-semibold leading-6 text-gray-900">
                  公司名稱
                </label>
                <div className="mt-2.5">
                  <input
                    type="text"
                    name="company"
                    id="company"
                    value={formData.company}
                    onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                    autoComplete="organization"
                    required
                    className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="email" className="block text-sm font-semibold leading-6 text-gray-900">
                  電子郵件
                </label>
                <div className="mt-2.5">
                  <input
                    type="email"
                    name="email"
                    id="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    autoComplete="email"
                    required
                    className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="phone" className="block text-sm font-semibold leading-6 text-gray-900">
                  聯絡電話
                </label>
                <div className="mt-2.5">
                  <input
                    type="tel"
                    name="phone"
                    id="phone"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                    autoComplete="tel"
                    required
                    className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6"
                  />
                </div>
              </div>
              <div className="sm:col-span-2">
                <label htmlFor="message" className="block text-sm font-semibold leading-6 text-gray-900">
                  需求說明
                </label>
                <div className="mt-2.5">
                  <textarea
                    name="message"
                    id="message"
                    value={formData.message}
                    onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                    rows={4}
                    required
                    className="block w-full rounded-md border-0 px-3.5 py-2 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6"
                  />
                </div>
              </div>
            </div>
            <div className="mt-10">
              <button
                type="submit"
                disabled={isSubmitting}
                className={`block w-full rounded-md px-3.5 py-2.5 text-center text-sm font-semibold text-white shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 ${
                  isSubmitting 
                    ? 'bg-blue-400 cursor-not-allowed'
                    : 'bg-blue-600 hover:bg-blue-500'
                }`}
              >
                {isSubmitting ? '提交中...' : '送出表單'}
              </button>
            </div>
            
            {submitStatus === 'success' && (
              <div className="mt-4 p-4 bg-green-50 text-green-700 rounded-md">
                表單提交成功！我們會盡快與您聯繫。
              </div>
            )}
            
            {submitStatus === 'error' && (
              <div className="mt-4 p-4 bg-red-50 text-red-700 rounded-md">
                提交失敗，請稍後再試或直接聯繫我們。
              </div>
            )}
          </form>
        </div>
      </div> */}

      {/* Contact Methods */}
      {/* <div className="bg-white">
        <div className="mx-auto max-w-7xl px-6 py-24 sm:py-32 lg:px-8">
          <div className="mx-auto max-w-2xl lg:max-w-4xl">
            <h2 className="text-2xl font-bold tracking-tight text-gray-900">聯絡方式</h2>
            <p className="mt-6 text-lg leading-8 text-gray-600">
              選擇最適合您的聯絡方式，我們將竭誠為您服務
            </p>
            <div className="mt-16 space-y-20">
              {contactMethods.map((method, index) => (
                <div
                  key={index}
                  className="grid grid-cols-1 gap-x-8 gap-y-6 md:grid-cols-3"
                >
                  <div>
                    <h3 className="text-base font-semibold leading-7 text-gray-900">
                      {method.name}
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-gray-600">
                      {method.description}
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <dl className="space-y-4">
                      <div>
                        <dt className="text-sm font-medium text-gray-600">電話</dt>
                        <dd>
                          <a
                            href={`tel:${method.phone}`}
                            className="text-sm leading-6 text-gray-900 hover:text-blue-600"
                          >
                            {method.phone}
                          </a>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-sm font-medium text-gray-600">電子郵件</dt>
                        <dd>
                          <a
                            href={`mailto:${method.email}`}
                            className="text-sm leading-6 text-gray-900 hover:text-blue-600"
                          >
                            {method.email}
                          </a>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-sm font-medium text-gray-600">服務時間</dt>
                        <dd className="text-sm leading-6 text-gray-900">{method.hours}</dd>
                      </div>
                    </dl>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div> */}

      {/* Office Location */}
      <div className="bg-gray-50">
        <div className="mx-auto max-w-7xl px-6 py-24 sm:py-32 lg:px-8">
          <div className="mx-auto max-w-2xl lg:max-w-4xl">
            <h2 className="text-2xl font-bold tracking-tight text-gray-900">聯絡方式</h2>
            
            <div className="mt-10 space-y-4">
              <p className="text-base leading-7 text-gray-600 flex items-center gap-2">
                <a
                  href="https://line.me/ti/p/@903yfago"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center group"
                  style={{ width: 'fit-content' }}
                >
                  <div className="relative">
                    {/* Line 圓形圖標 */}
                    <Image
                      src="/images/line-icon.jpg"
                      alt="Line"
                      width={56}
                      height={56}
                      className="rounded-full shadow-lg"
                    />
                    {/* 紅色通知角標 */}
                    <span className="absolute -top-1 -right-1 bg-red-600 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center border-2 border-white shadow">
                      1
                    </span>
                  </div>
                  {/* 對話框樣式 */}
                  <span className="relative ml-2 px-4 py-2 bg-white rounded-full shadow text-gray-800 text-lg font-bold
                    before:content-[''] before:absolute before:left-[-12px] before:top-1/2 before:-translate-y-1/2
                    before:w-0 before:h-0 before:border-y-8 before:border-y-transparent before:border-r-8 before:border-r-white">
                    加入好友，專人服務
                  </span>
                </a>
              </p>
              <p className="text-base leading-7 text-gray-600">
              Email：euhon_service@gmail.com
              </p>
              <p className="text-base leading-7 text-gray-600">
              地址：台北市安和路二段19號6F-1
              </p>  
              <p className="mt-6 text-lg leading-8 text-gray-600">
              歡迎蒞臨參觀，了解更多關於我們的服務
            </p>
            </div>
            <div className="mt-12 flex justify-center">
              <div className="w-full max-w-4xl rounded-xl overflow-hidden shadow-lg">
                <iframe
                  src="https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3615.054524228434!2d121.55016217539594!3d25.032223638363057!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x3442abcc677da21d%3A0x99446e6f9be8116c!2zMTA25Y-w5YyX5biC5aSn5a6J5Y2A5a6J5ZKM6Lev5LqM5q61MTnomZ82ZiAx!5e0!3m2!1szh-TW!2stw!4v1747362639480!5m2!1szh-TW!2stw"
                  width="100%"
                  height="500"
                  style={{ border: 0 }}
                  allowFullScreen={true}
                  loading="lazy"
                  referrerPolicy="no-referrer-when-downgrade"
                  title="公司位置"
                ></iframe>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
} 