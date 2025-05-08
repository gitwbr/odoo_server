"use client";

import { useState } from 'react';
import Navbar from '@/components/Navbar';

type FAQ = {
  question: string;
  answer: string;
};

type FAQCategory = {
  title: string;
  questions: FAQ[];
};

type FAQs = {
  [key: string]: FAQCategory;
};

const faqs: FAQs = {
  general: {
    title: '一般問題',
    questions: [
      {
        question: 'Euhon ERP 適合什麼規模的企業使用？',
        answer: '我們的系統適合各種規模的大圖輸出企業使用，從小型工作室到大型印刷廠都能靈活配置。系統模組化設計允許您根據需求選擇合適的功能。'
      },
      {
        question: '導入系統需要多長時間？',
        answer: '一般情況下，您註冊完之後可以直接創建系統進行試用，基礎系統可在幾分鐘內完成導入並開始使用。還可以升級更多功能的版本或者進行客製化定制'
      },
      {
        question: '系統是否提供培訓服務？',
        answer: '是的，我們提供完整的培訓服務，包括系統操作培訓、管理者培訓等。'
      }
    ]
  },
  technical: {
    title: '技術支援',
    questions: [
      {
        question: '系統是否支援行動裝置？',
        answer: '是的，Euhon ERP 提供完整的行動支援，您可以通過手機或平板隨時查看訂單狀態、處理審批事項等。'
      },
      {
        question: '系統如何確保數據安全？',
        answer: '我們採用業界標準的加密技術，定期數據備份，並提供多層次的權限管理，確保您的數據安全。'
      }/* ,
      {
        question: '是否支援與其他系統整合？',
        answer: '是的，我們提供標準的API接口，可以與您現有的財務系統、電商平台等進行整合。'
      } */
    ]
  },
  pricing: {
    title: '價格方案',
    questions: [
      {
        question: '收費方式是怎樣的？',
        answer: '我們提供靈活的收費方案，包括月付和年付選項。具體價格取決於您您的需求，可以聯繫我們獲取更多資訊。'
      },
      {
        question: '是否有免費試用？',
        answer: '是的，我們提供30天的免費試用期，讓您充分體驗系統功能。試用期間提供技術支援。'
      },
      {
        question: '後續維護費用如何收取？',
        answer: '系統使用費已包含基礎維護和升級服務。如需額外的客製化開發，我們會根據需求另行報價。'
      }
    ]
  },
  support: {
    title: '售後服務',
    questions: [
      {
        question: '提供哪些售後服務？',
        answer: '我們提供7x24小時技術支援，包括電話支援、在線客服、遠程協助等。定期進行系統更新和功能優化。'
      },
      {
        question: '如何處理系統問題？',
        answer: '我們設有專業的技術支援團隊，收到問題反饋後會立即處理。一般技術問題我們承諾在4小時內回應。'
      },
      {
        question: '是否提供實地支援？',
        answer: '是的，對於重要客戶，我們提供定期的實地拜訪服務，協助解決使用過程中的問題。'
      }
    ]
  }
};

export default function FAQ() {
  const [activeCategory, setActiveCategory] = useState<string>('general');

  return (
    <main className="flex min-h-screen flex-col">
      <Navbar />
      
      {/* Header */}
      <div className="bg-white px-6 py-24 sm:py-32 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-base font-semibold leading-7 text-blue-600">常見問答</h2>
          <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
            我們在這裡解答您的疑問
          </p>
          <p className="mt-6 text-lg leading-8 text-gray-600">
            找不到您想問的問題？歡迎聯繫我們的客服團隊
          </p>
        </div>
      </div>

      {/* FAQ Categories */}
      <div className="bg-gray-50">
        <div className="mx-auto max-w-7xl px-6 py-16 sm:py-24 lg:px-8">
          <div className="mx-auto max-w-4xl">
            {/* Category Tabs */}
            <div className="border-b border-gray-200">
              <nav className="-mb-px flex space-x-8" aria-label="Tabs">
                {Object.entries(faqs).map(([key, value]) => (
                  <button
                    key={key}
                    onClick={() => setActiveCategory(key)}
                    className={`
                      whitespace-nowrap border-b-2 py-4 px-1 text-sm font-medium
                      ${activeCategory === key
                        ? 'border-blue-600 text-blue-600'
                        : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'}
                    `}
                  >
                    {value.title}
                  </button>
                ))}
              </nav>
            </div>

            {/* FAQ List */}
            <dl className="mt-10 space-y-8">
              {faqs[activeCategory].questions.map((faq, index) => (
                <div key={index} className="bg-white p-8 rounded-2xl shadow-sm">
                  <dt className="text-lg font-semibold leading-7 text-gray-900">
                    {faq.question}
                  </dt>
                  <dd className="mt-4 text-base leading-7 text-gray-600">
                    {faq.answer}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </div>

      {/* Contact CTA */}
      <div className="bg-white">
        <div className="mx-auto max-w-7xl px-6 py-24 sm:py-32 lg:px-8">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              還有其他問題？
            </h2>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-gray-600">
              我們的專業團隊隨時為您服務，歡迎聯繫我們獲取更多資訊
            </p>
            <div className="mt-10 flex items-center justify-center gap-x-6">
              <a
                href="/contact"
                className="rounded-md bg-blue-600 px-3.5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
              >
                聯絡我們
              </a>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
} 