import { Link } from "react-router-dom";
import { ArrowLeft, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function NotFoundPage(): JSX.Element {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 flex items-center justify-center">
      <Card className="border-0 shadow-xl max-w-md w-full mx-4">
        <CardContent className="p-8 text-center">
          <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-lg">
            <Target className="h-10 w-10 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mb-3">页面不存在</h1>
          <p className="text-slate-600 mb-8">
            您访问的路径没有对应页面，请检查网址是否正确。
          </p>
          <Button 
            onClick={() => window.history.back()} 
            variant="outline"
            className="mr-3 border-slate-300 text-slate-700 hover:bg-slate-50"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            返回上一页
          </Button>
          <Link to="/">
            <Button className="bg-blue-600 hover:bg-blue-700">
              返回首页
            </Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
