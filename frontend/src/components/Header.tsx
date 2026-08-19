import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Shield, Moon, Sun, KeyRound, Image, Layers, FileText, History, Check } from 'lucide-react';
import { useDarkMode } from '../hooks/useDarkMode';
import { getApiKey, setApiKey } from '../utils/api';

const navItems = [
  { to: '/', label: 'Single Image', icon: Image },
  { to: '/batch', label: 'Batch', icon: Layers },
  { to: '/pdf', label: 'PDF', icon: FileText },
  { to: '/history', label: 'History', icon: History },
];

export const Header = () => {
  const { isDark, toggle } = useDarkMode();
  const [showSettings, setShowSettings] = useState(false);
  const [apiKey, setApiKeyDraft] = useState(getApiKey());
  const [saved, setSaved] = useState(false);

  const handleSaveKey = () => {
    setApiKey(apiKey.trim());
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1500);
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 glass-panel border-b mx-4 mt-4 px-6 py-3">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 shrink-0">
          <div className="p-2 bg-primary-600 rounded-lg">
            <Shield className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">RedactFlow</h1>
            <p className="text-xs text-gray-500 dark:text-gray-400">Intelligent Document Privacy</p>
          </div>
        </div>

        <nav className="hidden md:flex items-center gap-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-primary-600 text-white shadow-md'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-700'
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-2 shrink-0">
          <div className="relative">
            <button
              onClick={() => setShowSettings((s) => !s)}
              title="API key settings"
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-dark-700 transition-colors"
            >
              <KeyRound className="w-5 h-5 text-gray-600 dark:text-gray-300" />
            </button>
            {showSettings && (
              <div className="absolute right-0 mt-2 w-72 p-4 rounded-xl border border-gray-200 dark:border-dark-600 bg-white dark:bg-dark-800 shadow-xl">
                <label
                  htmlFor="api-key-input"
                  className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1"
                >
                  API Key (X-API-Key)
                </label>
                <input
                  id="api-key-input"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKeyDraft(e.target.value)}
                  placeholder="Leave empty if backend is open"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-dark-600 bg-white dark:bg-dark-900 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <button
                  onClick={handleSaveKey}
                  className="mt-2 w-full px-3 py-1.5 text-sm font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors flex items-center justify-center gap-1"
                >
                  {saved ? <Check className="w-4 h-4" /> : null}
                  {saved ? 'Saved' : 'Save'}
                </button>
                <p className="mt-2 text-[11px] text-gray-400">
                  Stored only in your browser's localStorage.
                </p>
              </div>
            )}
          </div>
          <button
            onClick={toggle}
            title="Toggle dark mode"
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-dark-700 transition-colors"
          >
            {isDark ? (
              <Sun className="w-5 h-5 text-yellow-400" />
            ) : (
              <Moon className="w-5 h-5 text-gray-600" />
            )}
          </button>
        </div>
      </div>

      {/* Mobile nav */}
      <nav className="md:hidden flex items-center justify-center gap-1 mt-2">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                isActive
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-dark-700'
              }`
            }
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
};
