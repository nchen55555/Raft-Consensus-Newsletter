import React, { useEffect, useState } from 'react';
import { Input, Button, notification } from 'antd';
import { motion } from 'framer-motion';
import Navigation from '@/components/Navigation';

interface SubscriptionGateProps {
  children: React.ReactNode;
  hideNav?: boolean; // Optionally hide nav for in-section use
  className?: string;
}

export default function SubscriptionGate({ children, hideNav = false, className = '' }: SubscriptionGateProps) {
  const [email, setEmail] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [showVerify, setShowVerify] = useState(false);
  const [api, contextHolder] = notification.useNotification();
  useEffect(() => {
    const storedEmail = sessionStorage.getItem('startupnews_email');
    if (storedEmail) setEmail(storedEmail);
  }, []);

  const handleSubscribe = () => {
    if (!input) {
      api.error({ message: 'Please enter your email.' });
      return;
    }
    sessionStorage.setItem('startupnews_email', input);
    setEmail(input);
    api.success({ message: 'Subscribed!' });
  };

  const handleVerify = () => {
    if (!input) {
      api.error({ message: 'Please enter your email.' });
      return;
    }
    // In a real app, verify email here
    sessionStorage.setItem('startupnews_email', input);
    setEmail(input);
    api.success({ message: 'Verified!' });
  };

  if (!email) {
    return (
      <div className={`flex flex-col items-center justify-center ${className}`}>
        {contextHolder}
        {!hideNav && (
          <div className="px-8 pt-8 w-full">
            <Navigation />
          </div>
        )}
        <div className="flex flex-col items-center justify-center flex-1 w-full">
          <motion.div 
            className="flex flex-col items-center justify-center py-16 px-4 max-w-2xl mx-auto text-center bg-white rounded-xl shadow-lg"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8 }}
          >
            <h1 className="text-3xl font-bold mb-6">Subscribe to Access Articles</h1>
            <p className="text-lg text-gray-700 mb-8">Only Startup News subscribers can access our full library of articles.</p>
            {!showVerify ? (
              <>
                <Input
                  placeholder="Enter your email to subscribe"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  className="mb-2"
                />
                <Button type="primary" size="large" className="mb-4 w-full max-w-xs" onClick={handleSubscribe}>Subscribe</Button>
                <div className="text-gray-500 mb-2">Already subscribed?</div>
                <Button type="link" onClick={() => setShowVerify(true)} className="mb-4">Verify your email</Button>
              </>
            ) : (
              <>
                <Input
                  placeholder="Enter your email to verify"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  className="mb-2"
                />
                <Button type="primary" onClick={handleVerify} className="w-full max-w-xs">Verify</Button>
                <Button type="link" onClick={() => setShowVerify(false)} className="mt-2">Back</Button>
              </>
            )}
          </motion.div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
