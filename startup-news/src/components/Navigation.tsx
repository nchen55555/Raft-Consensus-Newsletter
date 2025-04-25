'use client';

import React from 'react';
import { Menu } from 'antd';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { usePathname } from 'next/navigation';

export default function Navigation() {
  const pathname = usePathname();

  const menuItems = [
    {
      key: '/',
      label: <Link href="/">Welcome</Link>,
    },
    {
      key: '/news',
      label: <Link href="/news">Articles</Link>,
    },
    {
      key: 'about',
      label: 'About',
      children: [
        {
          key: 'who',
          label: <Link href="/who">Contributors</Link>,
        },
        {
          key: 'apply',
          label: <Link href="/apply">Apply to Contribute</Link>,
        },
        {
          key: 'login',
          label: <Link href="/login">Login</Link>,
        },      
      ],
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="w-full"
    >
      <Menu
        mode="horizontal"
        selectedKeys={[pathname]}
        items={menuItems}
        className="bg-transparent border-none font-medium text-lg"
        style={{
          display: 'flex',
          justifyContent: 'flex-start',
        }}
      />
    </motion.div>
  );
}