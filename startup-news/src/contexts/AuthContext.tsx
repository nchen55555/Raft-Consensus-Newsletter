'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

interface AuthContextType {
  isAuthenticated: boolean;
  userEmail: string | null;
  login: (email: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  userEmail: null,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    // Check if user is logged in on mount
    const email = sessionStorage.getItem('startupnews_email');  
    if (email) {
      setIsAuthenticated(true);
      setUserEmail(email);
    }

    // Listen for storage events to sync state across tabs
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'startupnews_email') {
        if (e.newValue) {
          setIsAuthenticated(true);
          setUserEmail(e.newValue);
        } else {
          setIsAuthenticated(false);
          setUserEmail(null);
        }
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  const login = (email: string) => {
    setIsAuthenticated(true);
    setUserEmail(email);
    sessionStorage.setItem('startupnews_email', email);  
  };

  const logout = () => {
    setIsAuthenticated(false);
    setUserEmail(null);
    sessionStorage.removeItem('startupnews_email');  
    router.push('/login');
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, userEmail, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
