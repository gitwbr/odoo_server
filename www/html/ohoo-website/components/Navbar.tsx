"use client";

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Bars3Icon, XMarkIcon } from '@heroicons/react/24/outline';

const navigation = [
  { name: '首頁', href: '/' },
  /* { name: '功能介紹', href: '/features' }, */
  { name: '功能介紹', href: '/features2' },
  { name: '案例分享', href: '/cases' },
  { name: '常見問答', href: '/faq' },
  { name: '關於我們', href: '/about' },
];

export default function Navbar() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [mobileMenuOpen]);

  return (
    <header className="relative inset-x-0 top-0 z-50 bg-white/80 backdrop-blur-sm">
      <nav className="flex items-center justify-between p-6 lg:px-8" aria-label="Global">
        <div className="flex lg:flex-1">
          <Link href="/" className="-m-1.5 p-1.5">
            <span className="block font-bold" style={{fontSize:'2.2rem', color:'#888888', lineHeight:'1.1', letterSpacing:'2px', display:'inline-block', width:'auto'}}>
              Euh<span style={{color:'#7B5A7B'}}>o</span>n
            </span>
            <span className="block text-lg font-bold" style={{color:'#888888',letterSpacing:'2px',marginTop:'-2px',width:'100%'}}>歐鴻網路科技</span>
          </Link>
        </div>
        <div className="flex lg:hidden">
          <button
            type="button"
            className="-m-2.5 inline-flex items-center justify-center rounded-md p-2.5 text-gray-700"
            onClick={() => setMobileMenuOpen(true)}
          >
            <span className="sr-only">開啟主選單</span>
            <Bars3Icon className="h-6 w-6" aria-hidden="true" />
          </button>
        </div>
        <div className="hidden lg:flex lg:gap-x-12">
          {navigation.map((item) => (
            <Link
              key={item.name}
              href={item.href}
              className="text-sm font-semibold leading-6 text-gray-900 hover:text-blue-600"
            >
              {item.name}
            </Link>
          ))}
        </div>
        <div className="hidden lg:flex lg:flex-1 lg:justify-end">
          <Link
            href="/contact"
            className="rounded-md bg-blue-600 px-3.5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
          >
            立即諮詢
          </Link>
        </div>
      </nav>
      <div className={`lg:hidden ${mobileMenuOpen ? 'absolute top-full left-0 w-full z-[9999]' : 'hidden'}`}>
        <div className="bg-white flex flex-col px-6 py-6 shadow-lg">
          <div className="flex items-center justify-between">
            <Link href="/" className="-m-1.5 p-1.5">
              <span className="block font-bold" style={{fontSize:'2.2rem', color:'#888888', lineHeight:'1.1', letterSpacing:'2px', display:'inline-block', width:'auto'}}>
                Euh<span style={{color:'#7B5A7B'}}>o</span>n
              </span>
              <span className="block text-lg font-bold" style={{color:'#888888',letterSpacing:'2px',marginTop:'-2px',width:'100%'}}>歐鴻網路科技</span>
            </Link>
            <button
              type="button"
              className="-m-2.5 rounded-md p-2.5 text-gray-700"
              onClick={() => setMobileMenuOpen(false)}
            >
              <span className="sr-only">關閉選單</span>
              <XMarkIcon className="h-6 w-6" aria-hidden="true" />
            </button>
          </div>
          <div className="flex-1 flex flex-col justify-center">
            <div className="space-y-2">
              {navigation.map((item) => (
                <Link
                  key={item.name}
                  href={item.href}
                  className="-mx-3 block rounded-lg px-3 py-2 text-base font-semibold leading-7 text-gray-900 hover:bg-gray-50"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {item.name}
                </Link>
              ))}
              <Link
                href="/contact"
                className="-mx-3 block rounded-lg px-3 py-2.5 text-base font-semibold leading-7 text-white bg-blue-600 hover:bg-blue-500 text-center"
                onClick={() => setMobileMenuOpen(false)}
              >
                立即諮詢
              </Link>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
} 