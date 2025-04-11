import Link from 'next/link';
import Navbar from '@/components/Navbar';

const features = [
  {
    title: '智能計價與報價',
    description: '符合本地才數計價、CRM訂單轉换，提高報價準確度達95%以上',
    icon: '📊'
  },
  {
    title: '庫存與生產管理',
    description: '自動扣料及損耗紀錄、智能存管理，減少庫存差異達60%',
    icon: '📦'
  },
  {
    title: '高效工作流程',
    description: '自動提醒工班、自動判定圖檔尺寸，提升工作效率達40%',
    icon: '⚡'
  },
  {
    title: '數據分析報表',
    description: '完整的进銷存報表、結案報告，助您做出明智的經營決策',
    icon: '📈'
  }
];

const testimonials = [
  {
    content: '導入Ohoo ERP後，我們的訂單處理時間減少了50%，客戶滿意度大幅提升。',
    author: '張經理',
    company: '大台北廣告'
  },
  {
    content: '系統非常容易上手，售後服務也很到位，是我們數位轉型的最佳選擇。',
    author: '李總監',
    company: '創意廣告印刷'
  }
];

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col">
      <Navbar />
      
      {/* Hero Section */}
      <div className="relative isolate pt-14">
        <div className="absolute inset-x-0 -top-40 -z-10 transform-gpu overflow-hidden blur-3xl sm:-top-80">
          <div className="relative left-[calc(50%-11rem)] aspect-[1155/678] w-[36.125rem] -translate-x-1/2 rotate-[30deg] bg-gradient-to-tr from-[#ff80b5] to-[#9089fc] opacity-30 sm:left-[calc(50%-30rem)] sm:w-[72.1875rem]" />
        </div>
        
        <div className="mx-auto max-w-7xl px-6 py-24 sm:py-32 lg:px-8">
          <div className="mx-auto max-w-2xl text-center">
            <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-6xl">
              大圖產業數位化轉型的最佳夥伴
            </h1>
            <p className="mt-6 text-lg leading-8 text-gray-600">
              告別傳统計價繁瑣、庫存管理混亂、生産流程延遲等困擾，Ohoo ERP 助您實現數位化轉型，提升競爭力
            </p>
            <div className="mt-10 flex items-center justify-center gap-x-6">
              <Link
                href="/dashboard"
                className="rounded-md bg-blue-600 px-3.5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
              >
                立即體驗
              </Link>
              <Link href="/features" className="text-sm font-semibold leading-6 text-gray-900">
                了解更多 <span aria-hidden="true">→</span>
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Features Section */}
      <div className="bg-white py-24 sm:py-32">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <div className="mx-auto max-w-2xl lg:text-center">
            <h2 className="text-base font-semibold leading-7 text-blue-600">效率提升</h2>
            <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              為什麼選擇 Ohoo ERP
            </p>
            <p className="mt-6 text-lg leading-8 text-gray-600">
              我們擁有多年大圖產業服務經驗，深入了解您的需求，提供最專業的解決方案
            </p>
          </div>
          <div className="mx-auto mt-16 max-w-2xl sm:mt-20 lg:mt-24 lg:max-w-none">
            <dl className="grid max-w-xl grid-cols-1 gap-x-8 gap-y-16 lg:max-w-none lg:grid-cols-4">
              {features.map((feature) => (
                <div key={feature.title} className="flex flex-col">
                  <dt className="flex items-center gap-x-3 text-base font-semibold leading-7 text-gray-900">
                    <span className="text-2xl">{feature.icon}</span>
                    {feature.title}
                  </dt>
                  <dd className="mt-4 flex flex-auto flex-col text-base leading-7 text-gray-600">
                    <p className="flex-auto">{feature.description}</p>
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </div>

      {/* Testimonials Section */}
      <div className="bg-gray-50 py-24 sm:py-32">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <div className="mx-auto max-w-xl text-center">
            <h2 className="text-lg font-semibold leading-8 tracking-tight text-blue-600">客戶見證</h2>
            <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              聽聽他們怎麼說
            </p>
          </div>
          <div className="mx-auto mt-16 flow-root max-w-2xl sm:mt-20 lg:mx-0 lg:max-w-none">
            <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-2">
              {testimonials.map((testimonial, index) => (
                <div key={index} className="relative bg-white p-10 shadow-sm ring-1 ring-gray-900/5 sm:rounded-3xl sm:p-12">
                  <blockquote className="text-xl font-semibold leading-8 tracking-tight text-gray-900">
                    <p>{`"${testimonial.content}"`}</p>
                  </blockquote>
                  <figcaption className="mt-8 flex items-center gap-x-4">
                    <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center text-xl">
                      {testimonial.author[0]}
                    </div>
                    <div>
                      <div className="font-semibold">{testimonial.author}</div>
                      <div className="text-gray-600">{testimonial.company}</div>
                    </div>
                  </figcaption>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* CTA Section */}
      <div className="bg-white">
        <div className="mx-auto max-w-7xl py-24 sm:px-6 sm:py-32 lg:px-8">
          <div className="relative isolate overflow-hidden bg-gray-900 px-6 py-24 text-center shadow-2xl sm:rounded-3xl sm:px-16">
            <h2 className="mx-auto max-w-2xl text-3xl font-bold tracking-tight text-white sm:text-4xl">
              準備好開始您的數位轉型之旅了嗎？
            </h2>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-gray-300">
              立即預約免費諮詢，了解 Ohoo ERP 如何幫助您提升業績！
            </p>
            <div className="mt-10 flex items-center justify-center gap-x-6">
              <Link
                href="/contact"
                className="rounded-md bg-white px-3.5 py-2.5 text-sm font-semibold text-gray-900 shadow-sm hover:bg-gray-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
              >
                立即預約
              </Link>
            </div>
            <div className="absolute -top-24 right-0 -z-10 transform-gpu blur-3xl" aria-hidden="true">
              <div className="aspect-[1404/767] w-[87.75rem] bg-gradient-to-r from-[#80caff] to-[#4f46e5] opacity-25" />
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
