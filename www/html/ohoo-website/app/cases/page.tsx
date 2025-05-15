"use client";

import { useState } from 'react';
import Navbar from '@/components/Navbar';

const cases = [
  {
    title: '大型印刷廠數位轉型',
    company: '',
    description: '通過導入 ＭegaBoard ERP 系統，成功實現生產流程數位化管理，提升30%生產效率。',
    results: [
      '訂單處理時間縮短50%',
      '生產排程優化，減少20%閒置時間',
      '庫存管理精準度提升至98%',
      '客戶滿意度提升40%'
    ]
  },
  {
    title: '中型廣告公司營運優化',
    company: '',
    description: '採用我們的解決方案後，顯著改善了專案管理效率，提高了報價準確性。',
    results: [
      '專案完成時間縮短35%',
      '報價準確度提升至95%',
      '客戶回購率提升25%',
      '營運成本降低15%'
    ]
  },
  {
    title: '小型設計工作室效率提升',
    company: '',
    description: '透過系統整合訂單和設計流程，大幅提升工作效率和客戶溝通品質。',
    results: [
      '行政作業時間減少60%',
      '客戶溝通時間縮短40%',
      '專案進度透明度提升',
      '營業額成長35%'
    ]
  }
];

export default function Cases() {
  const [selectedCase, setSelectedCase] = useState<number | null>(null);

  return (
    <main className="flex min-h-screen flex-col">
      <Navbar />
      
      {/* Header */}
      <div className="bg-white px-6 py-24 sm:py-32 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-base font-semibold leading-7 text-blue-600">案例分享</h2>
          <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
            客戶成功故事
          </p>
          <p className="mt-6 text-lg leading-8 text-gray-600">
            了解其他企業如何通過 ＭegaBoard ERP 實現數位轉型，提升營運效率
          </p>
        </div>
      </div>

      {/* Cases Grid */}
      <div className="bg-gray-50 py-24 sm:py-32">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <div className="mx-auto grid max-w-2xl grid-cols-1 gap-8 lg:mx-0 lg:max-w-none lg:grid-cols-3">
            {cases.map((caseItem, index) => (
              <div
                key={index}
                className="flex flex-col bg-white p-8 shadow-lg rounded-xl cursor-pointer transition-transform hover:scale-105"
                onClick={() => setSelectedCase(index)}
              >
                <div className="flex-1">
                  <h3 className="text-xl font-semibold text-gray-900">
                    {caseItem.title}
                  </h3>
                  <p className="mt-2 text-sm text-blue-600">
                    {caseItem.company}
                  </p>
                  <p className="mt-4 text-base text-gray-600">
                    {caseItem.description}
                  </p>
                </div>
                <div className="mt-6">
                  <button
                    className="text-sm font-semibold leading-6 text-blue-600 hover:text-blue-500"
                  >
                    了解更多 <span aria-hidden="true">→</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Case Detail Modal */}
      {selectedCase !== null && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
            <div
              className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
              onClick={() => setSelectedCase(null)}
            />
            <div className="relative transform overflow-hidden rounded-lg bg-white px-4 pb-4 pt-5 text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-2xl sm:p-6">
              <div>
                <div className="mt-3 text-center sm:mt-5">
                  <h3 className="text-2xl font-semibold leading-6 text-gray-900">
                    {cases[selectedCase].title}
                  </h3>
                  <p className="mt-2 text-sm text-blue-600">
                    {cases[selectedCase].company}
                  </p>
                  <div className="mt-8">
                    <p className="text-base text-gray-600">
                      {cases[selectedCase].description}
                    </p>
                    <div className="mt-6">
                      <h4 className="text-lg font-semibold text-gray-900">主要成效</h4>
                      <ul className="mt-4 space-y-4">
                        {cases[selectedCase].results.map((result, index) => (
                          <li
                            key={index}
                            className="flex items-center text-base text-gray-600"
                          >
                            <span className="mr-3 text-blue-600">•</span>
                            {result}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
              <div className="mt-8 sm:mt-12">
                <button
                  type="button"
                  className="mt-3 inline-flex w-full justify-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50 sm:mt-0"
                  onClick={() => setSelectedCase(null)}
                >
                  關閉
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* CTA Section */}
      <div className="bg-white">
        <div className="mx-auto max-w-7xl px-6 py-24 sm:py-32 lg:px-8">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              準備好開始了嗎？
            </h2>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-gray-600">
              立即聯繫我們，了解 ＭegaBoard ERP 如何幫助您的企業實現數位轉型
            </p>
            <div className="mt-10 flex items-center justify-center gap-x-6">
              <a
                href="/contact"
                className="rounded-md bg-blue-600 px-3.5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
              >
                免費諮詢
              </a>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
} 