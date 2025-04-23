'use client';

import Image from 'next/image';
import Navbar from '@/components/Navbar';

export default function Features2() {
  // 定义6个图片展示区域的数据
  const features = [
    { id: 1, title: '功能 1', image: '/images/features/feature1.jpg' },
    { id: 2, title: '功能 2', image: '/images/features/feature2.jpg' },
    { id: 3, title: '功能 3', image: '/images/features/feature3.jpg' },
    { id: 4, title: '功能 4', image: '/images/features/feature4.jpg' },
    { id: 5, title: '功能 5', image: '/images/features/feature5.jpg' },
    { id: 6, title: '功能 6', image: '/images/features/feature6.jpg' },
  ];

  return (
    <main className="flex min-h-screen flex-col">
      <Navbar />
      
      <div className="w-full max-w-[80%] mx-auto pt-20 pb-8">
        <div className="flex flex-col">
          {features.map((feature) => (
            <div key={feature.id} className="w-full relative h-[1500px] mb-20">
              <Image
                src={feature.image}
                alt={feature.title}
                fill
                style={{ 
                  objectFit: 'contain',
                  width: '100%'
                }}
                sizes="80vw"
                priority
              />
            </div>
          ))}
        </div>
      </div>
    </main>
  );
} 