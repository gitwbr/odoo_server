"use client";

import Navbar from '@/components/Navbar';

const teamMembers = [
  {
    name: '張志明',
    role: '創辦人兼執行長',
    description: '擁有超過15年大圖產業經驗，深入了解產業痛點，致力於推動產業數位化轉型。'
  },
  {
    name: '李美玲',
    role: '技術總監',
    description: '資深系統架構師，帶領團隊開發符合產業需求的創新解決方案。'
  },
  {
    name: '王建國',
    role: '客戶服務總監',
    description: '專注於提供最佳客戶體驗，確保客戶能夠充分運用系統提升營運效率。'
  }
];

const milestones = [
  {
    year: '2020',
    title: '公司成立',
    description: '由一群懷抱理想的產業專家共同創立，致力於解決大圖產業的營運痛點。'
  },
  {
    year: '2021',
    title: 'Ohoo ERP 1.0 發布',
    description: '推出第一版系統，獲得多家企業採用，並持續根據使用者回饋進行優化。'
  },
  {
    year: '2022',
    title: '完成 A 輪融資',
    description: '獲得知名創投投資，加速產品研發和市場擴展。'
  },
  {
    year: '2023',
    title: '推出全新 2.0 版本',
    description: '整合更多智能化功能，提供更完整的行動支援，協助企業實現真正的數位轉型。'
  }
];

export default function About() {
  return (
    <main className="flex min-h-screen flex-col">
      <Navbar />
      
      {/* Header */}
      <div className="bg-white px-6 py-24 sm:py-32 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-base font-semibold leading-7 text-blue-600">關於我們</h2>
          <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
            專注於大圖產業的數位化解決方案
          </p>
          <p className="mt-6 text-lg leading-8 text-gray-600">
            我們擁有多年大圖產業服務經驗，深入了解您的需求，提供最專業的解決方案
          </p>
        </div>
      </div>

      {/* Mission Section */}
      <div className="bg-blue-600 px-6 py-24 sm:py-32 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
            我們的使命
          </h2>
          <p className="mt-6 text-lg leading-8 text-blue-100">
            協助大圖產業實現數位化轉型，提升營運效率，創造更大的商業價值。
            我們相信，通過科技創新，能夠為產業帶來革命性的改變。
          </p>
        </div>
      </div>

      {/* Team Section */}
      <div className="bg-white py-24 sm:py-32">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <div className="mx-auto max-w-2xl lg:mx-0">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              我們的團隊
            </h2>
            <p className="mt-6 text-lg leading-8 text-gray-600">
              由一群充滿熱情的專業人士組成，致力於為客戶提供最佳服務
            </p>
          </div>
          <div className="mx-auto mt-16 grid max-w-2xl grid-cols-1 gap-x-8 gap-y-20 lg:mx-0 lg:max-w-none lg:grid-cols-3">
            {teamMembers.map((member, index) => (
              <div key={index} className="flex flex-col items-start">
                <div className="rounded-2xl bg-gray-100 p-2">
                  <div className="h-48 w-48 rounded-xl bg-gray-200 flex items-center justify-center text-4xl font-bold text-gray-500">
                    {member.name[0]}
                  </div>
                </div>
                <h3 className="mt-6 text-lg font-semibold leading-8 tracking-tight text-gray-900">
                  {member.name}
                </h3>
                <p className="text-base leading-7 text-blue-600">{member.role}</p>
                <p className="mt-4 text-base leading-7 text-gray-600">
                  {member.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Timeline Section */}
      <div className="bg-gray-50 py-24 sm:py-32">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <div className="mx-auto max-w-2xl lg:mx-0">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              發展歷程
            </h2>
            <p className="mt-6 text-lg leading-8 text-gray-600">
              見證我們的成長與創新
            </p>
          </div>
          <div className="mx-auto mt-16 max-w-2xl lg:mx-0">
            <div className="space-y-16">
              {milestones.map((milestone, index) => (
                <div
                  key={index}
                  className="flex flex-col gap-x-4 gap-y-6 lg:flex-row lg:items-start"
                >
                  <div className="flex-none text-3xl font-bold tracking-tight text-blue-600">
                    {milestone.year}
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold tracking-tight text-gray-900">
                      {milestone.title}
                    </h3>
                    <p className="mt-2 text-base leading-7 text-gray-600">
                      {milestone.description}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* CTA Section */}
      <div className="bg-white">
        <div className="mx-auto max-w-7xl px-6 py-24 sm:py-32 lg:px-8">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              加入我們的行列
            </h2>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-gray-600">
              立即體驗 Ohoo ERP，開啟您的數位化轉型之旅
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