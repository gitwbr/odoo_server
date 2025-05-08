'use client';

import Image from 'next/image';
import Navbar from '@/components/Navbar';

export default function Features2() {


  return (
    <main className="flex min-h-screen flex-col bg-white">
      <Navbar />
      <div className="w-full max-w-4xl mx-auto pt-24 pb-8 px-4 flex flex-col items-start">
        {/* 橘色竖条在主标题上方居左 */}
        <div className="w-12 md:w-16 h-24 md:h-32 bg-[#FFB84A] rounded-b-full mb-4 ml-8" style={{borderTopLeftRadius:0,borderTopRightRadius:0}}></div>
        {/* 主标题区块：主标题+蓝色横条 */}
        <div className="relative w-full mb-2 flex flex-col items-start" style={{minHeight:'110px'}}>
          {/* 主标题两行 */}
          <div className="flex items-center relative z-10">
            <span className="text-[2.6rem] md:text-[3.5rem] font-extrabold leading-[1.1] text-[#7B5A7B]" style={{letterSpacing:'2px'}}>MEGA</span>
          </div>
          <div className="flex items-center relative z-10 mt-[-0.2em]">
            <span className="text-[2.6rem] md:text-[3.5rem] font-extrabold leading-[1.1] text-[#7B5A7B]" style={{letterSpacing:'2px'}}>Board ERP</span>
          </div>
          {/* 蓝色横条绝对定位在右侧 */}
          <span
            className="hidden md:block absolute right-0 top-1/2 -translate-y-1/2 h-[60px] w-[500px] bg-[#4A7BFF] rounded-l-full"
            style={{borderTopRightRadius:0,borderBottomRightRadius:0}}
          ></span>
          <span
            className="block md:hidden absolute right-0 top-1/2 -translate-y-1/2 h-[48px] w-[100px] bg-[#4A7BFF] rounded-l-full"
            style={{borderTopRightRadius:0,borderBottomRightRadius:0}}
          ></span>
        </div>
        {/* 副标题区块：副标题三行 */}
        <div className="flex w-full items-start mb-8 mt-2">
          {/* 副标题三行 */}
          <div className="flex flex-col justify-center">
            <div className="text-[2rem] md:text-[2.5rem] font-extrabold leading-[1.1] text-[#888888]" style={{letterSpacing:'2px'}}>五大優勢帶您突圍重生</div>
          </div>
        </div>
        {/* 说明文字区块：红色竖条+说明文字 */}
        <div className="flex w-full items-start mt-8">
          {/* 红色竖条 */}
          <div className="w-12 md:w-16 h-60 md:h-35 bg-[#FF6B6B] rounded-t-full mr-4 ml-8 flex-shrink-0" style={{borderBottomLeftRadius:0,borderBottomRightRadius:0}}></div>
          {/* 说明文字 */}
          <div className="w-full text-gray-500 text-base md:text-lg leading-relaxed text-left">
          告別手忙腳亂的傳統管理瓶頸，昂首闊步邁向數位化轉型！我們的數位印刷專用ERP系統，Megaboard ERP基於強大的Odoo平台客製化精雕細琢而成，為您帶來五大核心優勢，一舉掃除大圖產業常見的客戶管理、庫存管理、生產管理、記帳管理等陳年痛點，助您在競爭激烈的市場中脫穎而出，贏得先機。
          </div>
        </div>
      </div>
      {/* 第一区块：客户管理与资讯透明 */}
      <div className="w-full max-w-4xl mx-auto mt-20 flex flex-col items-start">
        {/* 红色标题条 */}
        <div className="w-full flex items-center mb-8">
          <div className="h-14 md:h-16 px-8 flex items-center bg-[#FF6B6B] rounded-r-full" style={{borderTopLeftRadius:0,borderBottomLeftRadius:0}}>
            <span className="text-white text-2xl md:text-3xl font-extrabold tracking-wide">客戶管理與資訊透明</span>
          </div>
        </div>
        {/* 4个图标+标题+描述，支持响应式 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-8 w-full">
          {/* 1 */}
          <div className="flex flex-col items-center text-center">
            <Image src="/images/features/1.png" alt="強化業務協作" width={64} height={64} className="h-16 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">強化業務協作</div>
            <div className="text-gray-500 text-xs">這不僅大幅提升客戶服務與重複銷售的精準度與個人化，更對業務接手交接非常有幫助，確保客戶關係不中斷。</div>
          </div>
          {/* 2 */}
          <div className="flex flex-col items-center text-center">
            <Image src="/images/features/2.png" alt="銷售、庫存、報表整合" width={64} height={64} className="h-16 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">銷售、庫存、報表整合</div>
            <div className="text-gray-500 text-xs">Megaboard ERP 提供完整的銷售流程記錄、即時庫存狀態與可視化報表，讓每個人都能在系統內一目瞭然最新資訊。</div>
          </div>
          {/* 3 */}
          <div className="flex flex-col items-center text-center">
            <Image src="/images/features/3.png" alt="數據化客戶資料" width={64} height={64} className="h-16 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">數據化客戶資料</div>
            <div className="text-gray-500 text-xs">所有內容集中在同一系統內，全面數據化管理。人員能夠彈指間查詢客戶的報價紀錄與出貨情形，避免資訊散落四處的紙本或Excel，實現個人化服務與精準行銷。</div>
          </div>
          {/* 4 */}
          <div className="flex flex-col items-center text-center">
            <Image src="/images/features/4.png" alt="生產連動庫存" width={64} height={64} className="h-16 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">生產連動庫存</div>
            <div className="text-gray-500 text-xs">客戶下單成功則大圖訂單即時產生新訂單，生產各項產品扣料以便精準更新庫存。報表可將各項機台、業務出貨、廠商來往等等數據化追蹤，讓您對營運狀況瞭若指掌。</div>
          </div>
        </div>
      </div>
      {/* 第二区块：远端办公与系统整合 */}
      <div className="w-full max-w-4xl mx-auto mt-20 flex flex-col items-start">
        {/* 蓝色标题条 */}
        <div className="w-full flex items-center mb-8">
          <div className="h-14 md:h-16 px-8 flex items-center bg-[#4A7BFF] rounded-r-full" style={{borderTopLeftRadius:0,borderBottomLeftRadius:0}}>
            <span className="text-white text-2xl md:text-3xl font-extrabold tracking-wide">遠端辦公與系統整合</span>
          </div>
        </div>
        {/* 4个图标+标题+描述，支持响应式 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-8 w-full">
          {/* 1 */}
          <div className="flex flex-col items-center text-center">
            <Image src="/images/features/5.png" alt="遠端辦公，工作零界限" width={64} height={64} className="h-16 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">遠端辦公，工作零界限</div>
            <div className="text-gray-500 text-xs">可透過瀏覽器及APP操作，讓業務人員或主管即使不在公司也能查詢訂單、填寫報價。隨時隨地，工作不中斷。對於有外勤需求、異地辦公的企業來說，是非常實用且彈性的神兵利器。</div>
          </div>
          {/* 2 */}
          <div className="flex flex-col items-center text-center">
            <Image src="/images/features/6.png" alt="一站式管理" width={64} height={64} className="h-16 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">一站式管理</div>
            <div className="text-gray-500 text-xs">從銷售、庫存、會計到採購都可利用系統處理，不需要使用多套系統(如CRM用A、庫存用B、會計用C)，避免資料各自為政的問題。</div>
          </div>
          {/* 3 */}
          <div className="flex flex-col items-center text-center">
            <Image src="/images/features/7.png" alt="流程自動串聯" width={64} height={64} className="h-16 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">流程自動串聯</div>
            <div className="text-gray-500 text-xs">這樣不但大幅降低整合成本,資料流程從前端到後端皆可行雲流水自動串聯。</div>
          </div>
          {/* 4 */}
          <div className="flex flex-col items-center text-center">
            <Image src="/images/features/8.png" alt="EIP線上簽核" width={64} height={64} className="h-16 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">EIP線上簽核</div>
            <div className="text-gray-500 text-xs">電子化簽核流程，讓公司內部的簽核（例如報帳單、採購單等）可以線上進行，而不需紙本流轉。</div>
          </div>
        </div>
      </div>
      {/* 第三区块：CRM整合與數據驅動決策 + 24小時自動接單系統 */}
      {/* 上半部分：橘色大标题及两组内容 */}
      <div className="w-full max-w-4xl mx-auto mt-20 flex flex-col items-start">
        {/* 橘色标题条 */}
        <div className="w-full flex items-center mb-8">
          <div className="h-14 md:h-16 px-8 flex items-center bg-[#FFB84A] rounded-r-full" style={{borderTopLeftRadius:0,borderBottomLeftRadius:0}}>
            <span className="text-white text-2xl md:text-3xl font-extrabold tracking-wide">CRM整合與數據驅動決策</span>
          </div>
        </div>
        {/* 两组内容，响应式左右排列 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-12 w-full">
          {/* 左侧 */}
          <div className="flex flex-col items-center md:items-start text-center md:text-left">
            <Image src="/images/features/9.png" alt="CRM整合" width={72} height={72} className="h-20 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">CRM整合：固若金湯的客戶關係</div>
            <div className="text-gray-500 text-xs mb-2">完整客戶互動紀錄： CRM模組不僅能記錄潛在客戶與開發進度，還能保留客戶資料、紀錄對話內容、跟進備註等資料，並直接串接到報價單與訂單流程。</div>
            <div className="text-gray-500 text-xs">提升客戶滿意度： 每一筆客戶的互動都有鉅細靡遺的紀錄，不論是業務A或業務B都能無縫接軌，減少「人走資訊就斷」的窘境。
            </div>
          </div>
          {/* 右侧 */}
          <div className="flex flex-col items-center md:items-start text-center md:text-left">
            <Image src="/images/features/10.png" alt="數據驅動決策" width={72} height={72} className="h-20 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">數據驅動決策：精準制導企業成長</div>
            <div className="text-gray-500 text-xs mb-2">自動生成管理報表： 像是產品銷售表現、客戶貢獻度、毛利分析、應收帳款狀況等，即時幫助老闆與主管精準掌握企業營運現況。這些資料不再需要人工披星戴月統整，系統一鍵自動生成，提升決策速度與正確性。
            </div>
            <div className="text-gray-500 text-xs">精準策略調整： 透過數據，管理者可以更有信心地調整策略、調派人力或設定業績目標，帶領企業乘風破浪，再創高峰。
            </div>
          </div>
        </div>
      </div>
      {/* 下半部分：红色大标题及三组内容 */}
      <div className="w-full max-w-4xl mx-auto mt-20 flex flex-col items-start">
        {/* 红色标题条 */}
        <div className="w-full flex items-center mb-8">
          <div className="h-14 md:h-16 px-8 flex items-center bg-[#FF6B6B] rounded-r-full" style={{borderTopLeftRadius:0,borderBottomLeftRadius:0}}>
            <span className="text-white text-2xl md:text-3xl font-extrabold tracking-wide">24小時自動接單系統</span>
          </div>
        </div>
        {/* 三组内容，响应式排列 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 w-full">
          {/* 1 */}
          <div className="flex flex-col items-center text-center">
            <Image src="/images/features/11.png" alt="24小時自助下單" width={64} height={64} className="h-16 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">24小時自助下單</div>
            <div className="text-gray-500 text-xs">客戶可透過專屬入口自行下單，無須依賴人工回覆，系統自動記錄與處理訂單。全天候接單，絕不漏單，大幅提升接單效率，減少人為錯誤與漏單風險，特別適合處理大量與重複性訂單。</div>
          </div>
          {/* 2 */}
          <div className="flex flex-col items-center text-center">
            <Image src="/images/features/12.png" alt="即時自助報價" width={64} height={64} className="h-16 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">即時自助報價</div>
            <div className="text-gray-500 text-xs">系統依據客戶所選產品、規格與數量自動計算報價、稅額，報價透明即時，減少報價往返與等待時間，光速提升客戶決策速度與體驗。</div>
          </div>
          {/* 3 */}
          <div className="flex flex-col items-center text-center">
            <Image src="/images/features/13.png" alt="客戶進度查詢" width={64} height={64} className="h-16 mb-2" />
            <div className="text-[#7B5A7B] font-bold text-base mb-1">客戶進度查詢</div>
            <div className="text-gray-500 text-xs">客戶可隨時登入平台查詢訂單處理進度，減少來電查詢頻率，大幅降低客服壓力，提升企業專業形象與信任感。</div>
          </div>
        </div>
      </div>
      {/* 第四区块：ERP導入前後績效與功能差異 */}
      <div className="w-full max-w-4xl mx-auto mt-20 flex flex-col items-center">
        {/* 蓝色大标题条 */}
        <div className="w-full flex justify-center mb-8">
          <div className="bg-[#4A7BFF] rounded-full px-8 py-4 flex items-center justify-center shadow-md">
            <span className="text-white text-2xl md:text-3xl font-extrabold tracking-wide text-center">ERP導入前後績效與功能差異</span>
          </div>
        </div>
        {/* 表格区块 */}
        <div className="w-full overflow-x-auto">
          <table className="min-w-[700px] w-full text-center border-separate border-spacing-y-2">
            <thead>
              <tr>
                <th className="bg-[#B3C9FF] text-[#4A7BFF] font-bold py-3 px-2 rounded-l-xl min-w-[120px]">功能 / 績效指標</th>
                <th className="bg-[#E6EDFF] text-[#4A7BFF] font-bold py-3 px-2 min-w-[110px]">導入ERP前</th>
                <th className="bg-[#E6EDFF] text-[#4A7BFF] font-bold py-3 px-2 min-w-[110px]">導入ERP後（預期）</th>
                <th className="bg-[#E6EDFF] text-[#4A7BFF] font-bold py-3 px-2 rounded-r-xl min-w-[110px]">導入ERP後（預期）</th>
              </tr>
            </thead>
            <tbody className="text-sm md:text-base">
              <tr className="bg-[#F7FAFF]">
                <td className="font-bold py-2 px-2">訂單處理時間</td>
                <td>平均2小時/單</td>
                <td>平均5分鐘/單</td>
                <td className="text-[#4A7BFF] font-bold">減少96%</td>
              </tr>
              <tr className="bg-white">
                <td className="font-bold py-2 px-2">報價錯誤率</td>
                <td>約5%</td>
                <td>1%</td>
                <td className="text-[#4A7BFF] font-bold">減少99%</td>
              </tr>
              <tr className="bg-[#F7FAFF]">
                <td className="font-bold py-2 px-2">庫存盤點時間</td>
                <td>4小時/月</td>
                <td>1小時/月</td>
                <td className="text-[#4A7BFF] font-bold">減少75%</td>
              </tr>
              <tr className="bg-white">
                <td className="font-bold py-2 px-2">客戶詢問訂單進度頻率</td>
                <td>平均10次/天</td>
                <td>平均1次/天</td>
                <td className="text-[#4A7BFF] font-bold">減少90%</td>
              </tr>
              <tr className="bg-[#F7FAFF]">
                <td className="font-bold py-2 px-2">業務人員客戶拜訪量</td>
                <td>平均3次/週</td>
                <td>平均5次/週</td>
                <td className="text-[#FFB84A] font-bold">增加67%</td>
              </tr>
              <tr className="bg-white">
                <td className="font-bold py-2 px-2">管理報表產出時間</td>
                <td>1天/月</td>
                <td>即時</td>
                <td className="text-[#4A7BFF] font-bold">減少96%</td>
              </tr>
              <tr className="bg-[#F7FAFF]">
                <td className="font-bold py-2 px-2">客戶滿意度</td>
                <td>平均3.5/5分</td>
                <td>平均4.5/5分</td>
                <td className="text-[#FF6B6B] font-bold">提升29%</td>
              </tr>
              <tr className="bg-white">
                <td className="font-bold py-2 px-2">資訊透明度</td>
                <td>各部門資訊分散</td>
                <td>全公司資訊整合</td>
                <td className="text-[#4A7BFF] font-bold">顯著提升</td>
              </tr>
              <tr className="bg-[#F7FAFF]">
                <td className="font-bold py-2 px-2">遠端工作支援</td>
                <td>有限</td>
                <td>全面支援</td>
                <td className="text-[#4A7BFF] font-bold">顯著提升</td>
              </tr>
              <tr className="bg-white">
                <td className="font-bold py-2 px-2">系統整合程度</td>
                <td>多套系統，整合困難</td>
                <td>單一系統，無縫整合</td>
                <td className="text-[#4A7BFF] font-bold">顯著提升</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
} 