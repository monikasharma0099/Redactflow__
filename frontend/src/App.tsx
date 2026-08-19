import { Routes, Route } from 'react-router-dom';
import { Header } from './components/Header';
import { HomePage } from './pages/HomePage';
import { BatchPage } from './pages/BatchPage';
import { PDFPage } from './pages/PDFPage';
import { HistoryPage } from './pages/HistoryPage';

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-dark-900 transition-colors duration-300">
      <Header />

      <main className="pt-36 md:pt-28 pb-12 px-4 max-w-6xl mx-auto">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/batch" element={<BatchPage />} />
          <Route path="/pdf" element={<PDFPage />} />
          <Route path="/history" element={<HistoryPage />} />
        </Routes>
      </main>

      <footer className="text-center py-8 text-sm text-gray-500 dark:text-gray-600 border-t border-gray-200 dark:border-dark-800">
        <p>RedactFlow v2.0.0 • Built with FastAPI + React • Privacy-First Processing</p>
      </footer>
    </div>
  );
}
