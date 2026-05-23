import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "@/app/layout/AppShell";
import { HomePage } from "@/pages/HomePage";
import { NewRunPage } from "@/pages/NewRunPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { RunTracePage } from "@/pages/RunTracePage";
import { RunViewPage } from "@/pages/RunViewPage";
import { SkillStagingPage } from "@/pages/SkillStagingPage";

export const appRouter = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <HomePage />,
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
        path: "skills/staging",
        element: <SkillStagingPage />,
      },
      {
        path: "*",
        element: <NotFoundPage />,
      },
    ],
  },
]);
