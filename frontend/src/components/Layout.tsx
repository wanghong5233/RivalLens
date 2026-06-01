import { Link, useLocation } from "react-router-dom";
import { Sparkles } from "lucide-react";

interface LayoutProps {
  children: React.ReactNode;
  title?: string;
}

export function Layout({ children, title }: LayoutProps): JSX.Element {
  const location = useLocation();
  
  const navItems = [
    { path: "/", label: "首页" },
    { path: "/runs/new", label: "新建分析" },
    { path: "/skills/staging", label: "Skill 审核台" },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 grid-bg">
      {/* Header */}
      <header className="sticky top-0 z-50 glass border-b border-slate-100/50 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2 group">
              <div className="relative">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center transition-transform duration-300 group-hover:scale-110 group-hover:rotate-12">
                  <Sparkles className="h-4 w-4 text-white" />
                </div>
                <div className="absolute inset-0 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg blur-md opacity-50 group-hover:opacity-75 transition-opacity" />
              </div>
              <span className="font-semibold text-slate-900 gradient-text">RivalLens</span>
            </Link>
            
            <nav className="flex items-center gap-1">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 relative group ${
                    location.pathname === item.path
                      ? "bg-blue-50 text-blue-600"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  {item.label}
                  {location.pathname === item.path && (
                    <span className="absolute inset-0 bg-gradient-to-r from-blue-500/20 to-purple-500/20 rounded-lg animate-pulse-glow" />
                  )}
                </Link>
              ))}
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-4 py-8 animate-slide-up">
        {title && (
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-slate-900 gradient-text">{title}</h1>
          </div>
        )}
        {children}
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 bg-white border-t border-slate-100 mt-auto">
        <div className="max-w-4xl mx-auto text-center">
          <div className="flex items-center justify-center gap-2 mb-2">
            <div className="w-6 h-6 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
              <Sparkles className="h-3 w-3 text-white" />
            </div>
            <span className="font-semibold text-slate-900 gradient-text">RivalLens</span>
          </div>
          <p className="text-sm text-slate-500">
            AI 驱动的竞品分析平台
          </p>
        </div>
      </footer>
    </div>
  );
}