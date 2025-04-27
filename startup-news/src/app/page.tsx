'use client';

import React from 'react';
import Navigation from '@/components/Navigation';
import { TeamOutlined, NotificationOutlined, SmileOutlined, UserOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { Input, Card, Space } from 'antd';
import { motion } from 'framer-motion';
import Subscribe from '@/components/Subscribe';

export default function Blog() {
  const fadeInUp = {
    initial: { opacity: 0, y: 20 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.6 }
  };

  const features = [
    {
      icon: <NotificationOutlined className="text-3xl" />,
      title: "Expert Interviews",
      description: "Deep-dive conversations with founding team members across Engineering, Sales, and Marketing"
    },
    {
      icon: <SmileOutlined className="text-3xl" />,
      title: "Technical Deep-Dives",
      description: "Understand product architectures and the technical challenges of scaling"
    },
    {
      icon: <TeamOutlined className="text-3xl" />,
      title: "Strategic Insights",
      description: "Analysis of competitive landscapes and business strategies"
    }
  ];

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-gray-50">
      <div className="px-8 pt-8">
        <Navigation/>
      </div>
      
      {/* Hero Section */}
      <motion.div 
        className="flex flex-col items-center justify-center min-h-[70vh] px-4 max-w-6xl mx-auto text-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8 }}
      >
        <motion.div {...fadeInUp}>
          <h1 className="text-5xl font-bold mb-6 bg-gradient-to-r from-black to-gray-600 bg-clip-text text-transparent">
            The Seedling 🌱
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto leading-relaxed mb-8">
            Cut through the noise. Get real insights from startup founders building the next generation of technology companies.
          </p>
        </motion.div>
      </motion.div>

      {/* Newsletter Section */}
      <motion.div 
        className="py-20 bg-black text-white"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        transition={{ duration: 0.8 }}
        viewport={{ once: true }}
      >
        <div className="max-w-xl mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold mb-4">Stay in the Loop</h2>
          <p className="text-gray-400 mb-8">One curated startup deep-dive every week. No fluff, just insights.</p>
          <Subscribe />
        </div>
    </motion.div>

      {/* Features Section */}
      <div className="py-20 bg-white">
        <div className="max-w-6xl mx-auto px-4">
          <motion.div 
            className="grid md:grid-cols-3 gap-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
          >
            {features.map((feature, index) => (
              <Card 
                key={index}
                className="hover:shadow-lg transition-all duration-300 border-none bg-gray-50"
                styles={{ body: { padding: '2rem' } }}
              >
                <Space direction="vertical" size="middle" className="text-center">
                  <div className="text-black">{feature.icon}</div>
                  <h3 className="text-xl font-semibold">{feature.title}</h3>
                  <p className="text-gray-600">{feature.description}</p>
                </Space>
              </Card>
            ))}
          </motion.div>
        </div>
      </div>

    </div>
  );
}