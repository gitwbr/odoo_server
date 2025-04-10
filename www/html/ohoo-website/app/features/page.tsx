import Navbar from '@/components/Navbar';

const features = [
  {
    title: '智能計價與報價系統',
    description: '根據材料、尺寸、工藝等自動計算報價，提供專業的報價單',
    details: [
      '符合本地才數計價標準',
      'CRM訂單自動轉換',
      '多種報價模板選擇',
      '歷史報價查詢與分析'
    ]
  },
  {
    title: '庫存與生產管理',
    description: '完整的庫存追蹤系統，確保材料管理的準確性',
    details: [
      '自動扣料及損耗記錄',
      '庫存預警提醒',
      '材料使用分析報表',
      '供應商管理系統'
    ]
  },
  {
    title: '工單流程管理',
    description: '數位化工單流程，提高生產效率',
    details: [
      '自動生成施工單',
      '工單掃碼進度追蹤',
      '即時工作進度查看',
      '異常狀況即時通報'
    ]
  },
  {
    title: '行動裝置支援',
    description: '隨時隨地掌握生產狀況，提高管理效率',
    details: [
      '手機APP即時查看',
      '工班進度回報系統',
      '即時訊息通知',
      '行動簽核功能'
    ]
  },
  {
    title: '報表與分析工具',
    description: '全方位的數據分析，協助決策制定',
    details: [
      '銷售分析報表',
      '生產效率分析',
      '成本分析報表',
      '客戶訂單分析'
    ]
  },
  {
    title: '系統整合能力',
    description: '與其他系統無縫對接，提供完整解決方案',
    details: [
      '電子商務平台整合',
      '會計系統整合',
      '第三方支付整合',
      'API介面開放'
    ]
  }
];

export default function Features() {
  return (
    <main className="flex min-h-screen flex-col">
      <Navbar />
      
      {/* Header */}
      <div className="bg-white px-6 py-24 sm:py-32 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-base font-semibold leading-7 text-blue-600">功能介紹</h2>
          <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
            專為大圖產業打造的完整解決方案
          </p>
          <p className="mt-6 text-lg leading-8 text-gray-600">
            從訂單管理到生產追蹤，從庫存控制到數據分析，Ohoo ERP 提供您所需的一切功能
          </p>
        </div>
      </div>

      {/* Features Grid */}
      <div className="bg-gray-50 py-24 sm:py-32">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <div className="mx-auto grid max-w-2xl grid-cols-1 gap-x-8 gap-y-16 sm:gap-y-20 lg:mx-0 lg:max-w-none lg:grid-cols-3">
            {features.map((feature, index) => (
              <div key={index} className="bg-white p-8 rounded-2xl shadow-sm">
                <h3 className="text-xl font-semibold leading-7 text-gray-900">
                  {feature.title}
                </h3>
                <p className="mt-4 text-base leading-7 text-gray-600">
                  {feature.description}
                </p>
                <ul className="mt-8 space-y-3">
                  {feature.details.map((detail, detailIndex) => (
                    <li key={detailIndex} className="flex gap-x-3">
                      <svg
                        className="h-6 w-5 flex-none text-blue-600"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                        aria-hidden="true"
                      >
                        <path
                          fillRule="evenodd"
                          d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
                          clipRule="evenodd"
                        />
                      </svg>
                      <span className="text-gray-600">{detail}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CTA Section */}
      <div className="bg-white">
        <div className="mx-auto max-w-7xl px-6 py-24 sm:py-32 lg:px-8">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              想了解更多功能細節？
            </h2>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-gray-600">
              我們的專業團隊隨時為您服務，為您詳細介紹系統功能，並提供專屬的解決方案
            </p>
            <div className="mt-10 flex items-center justify-center gap-x-6">
              <a
                href="/contact"
                className="rounded-md bg-blue-600 px-3.5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
              >
                預約展示
              </a>
              <a
                href="/cases"
                className="text-sm font-semibold leading-6 text-gray-900"
              >
                查看案例 <span aria-hidden="true">→</span>
              </a>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
} 