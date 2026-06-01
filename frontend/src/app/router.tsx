import { createBrowserRouter } from "react-router-dom";

import { AgentRolesPage } from "@/pages/AgentRolesPage";
import { CompetitorComparePage } from "@/pages/CompetitorComparePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { EvidenceDetailPage } from "@/pages/EvidenceDetailPage";
import { FeedbackLoopPage } from "@/pages/FeedbackLoopPage";
import { FeaturesPage } from "@/pages/FeaturesPage";
import { HomePage } from "@/pages/HomePage";
import { NewRunPage } from "@/pages/NewRunPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { ReportExportPage } from "@/pages/ReportExportPage";
import { RunEvidencePage } from "@/pages/RunEvidencePage";
import { RunListPage } from "@/pages/RunListPage";
import { RunTracePage } from "@/pages/RunTracePage";
import { RunViewPage } from "@/pages/RunViewPage";
import { SchemaDetailPage } from "@/pages/SchemaDetailPage";
import { SkillStagingPage } from "@/pages/SkillStagingPage";
import { SurveyPage } from "@/pages/SurveyPage";

export const appRouter = createBrowserRouter([
  {
    path: "/",
    element: <HomePage />,
  },
  {
    path: "features",
    element: <FeaturesPage />,
  },
  {
    path: "dashboard",
    element: <DashboardPage />,
  },
  {
    path: "feedback",
    element: <FeedbackLoopPage />,
  },
  {
    path: "runs",
    element: <RunListPage />,
  },
  {
    path: "runs/new",
    element: <NewRunPage />,
  },
  {
    path: "runs/:runId",
    element: <RunViewPage />,
  },
  {
    path: "runs/:runId/trace",
    element: <RunTracePage />,
  },
  {
    path: "runs/:runId/evidence",
    element: <RunEvidencePage />,
  },
  {
    path: "runs/:runId/evidence/:evidenceId",
    element: <EvidenceDetailPage />,
  },
  {
    path: "runs/:runId/schema",
    element: <SchemaDetailPage />,
  },
  {
    path: "runs/:runId/agents",
    element: <AgentRolesPage />,
  },
  {
    path: "runs/:runId/compare",
    element: <CompetitorComparePage />,
  },
  {
    path: "runs/:runId/survey",
    element: <SurveyPage />,
  },
  {
    path: "runs/:runId/export",
    element: <ReportExportPage />,
  },
  {
    path: "skills/staging",
    element: <SkillStagingPage />,
  },
  {
    path: "*",
    element: <NotFoundPage />,
  },
]);
