import React, { useState } from 'react';
import { Input } from 'antd';
import { UserOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { motion } from 'framer-motion';

export default function Subscribe() {
  const [email, setEmail] = useState('');
  const [subscribed, setSubscribed] = useState(false);

  const handleSubscribe = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email,
        })
      });
      const result = await res.json();
      if (result.success) setSubscribed(true);
      else alert("Subscription failed: " + result.error);
    } catch (err) {
      console.error(err);
      alert("Subscription failed.");
    }
  };

  return (
    <div className="space-y-4">
      <Input 
        size="large"
        value={email}
        onChange={e => setEmail(e.target.value)}
        placeholder="example@gmail.com"
        prefix={<UserOutlined className="text-gray-400" />}
        className="rounded-lg"
      />
      <motion.button 
        className="w-full bg-white text-black py-3 px-6 rounded-lg font-medium hover:bg-gray-100 transition-colors flex items-center justify-center gap-2 group"
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        onClick={handleSubscribe}
      >
        {subscribed ? "Subscribed!" : "Subscribe Now"}
        <ArrowRightOutlined className="group-hover:translate-x-1 transition-transform" />
      </motion.button>
    </div>
  );
}
