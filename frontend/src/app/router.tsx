import { createBrowserRouter, Navigate, redirect } from "react-router-dom";

import { MarketingShell } from "@/app/layout/MarketingShell";
import { WorkspaceShell } from "@/app/layout/WorkspaceShell";
import { NotFoundPage } from "@/pages/NotFoundPage";

export const appRouter = createBrowserRouter([
  {
    path: "/",
    element: <MarketingShell />,
    children: [
      {
        index: true,
        lazy: async () => {
          const module = await import("@/pages/marketing/LandingPage");
          return { Component: module.LandingPage };
        },
      },
      {
        path: "pricing",
        lazy: async () => {
          const module = await import("@/pages/marketing/PricingPage");
          return { Component: module.PricingPage };
        },
      },
      {
        path: "examples",
        lazy: async () => {
          const module = await import("@/pages/marketing/ExamplesPage");
          return { Component: module.ExamplesPage };
        },
      },
      {
        path: "share/:runId",
        lazy: async () => {
          const module = await import("@/pages/marketing/SharedReportPage");
          return { Component: module.SharedReportPage };
        },
      },
      {
        path: "app",
        element: <WorkspaceShell />,
        children: [
          {
            index: true,
            lazy: async () => {
              const module = await import("@/pages/app/DashboardPage");
              return { Component: module.DashboardPage };
            },
          },
          {
            path: "runs/new",
            lazy: async () => {
              const module = await import("@/pages/NewRunChatPage");
              return { Component: module.NewRunChatPage };
            },
          },
          {
            path: "runs/new/expert",
            lazy: async () => {
              const module = await import("@/pages/NewRunPage");
              return { Component: module.NewRunPage };
            },
          },
          {
            path: "runs/:runId",
            lazy: async () => {
              const module = await import("@/pages/RunViewPage");
              return { Component: module.RunViewPage };
            },
          },
          {
            path: "runs/:runId/plan",
            lazy: async () => {
              const module = await import("@/pages/PlanConfirmPage");
              return { Component: module.PlanConfirmPage };
            },
          },
          {
            path: "runs/:runId/live",
            lazy: async () => {
              const module = await import("@/pages/LiveRunPage");
              return { Component: module.LiveRunPage };
            },
          },
          {
            path: "runs/:runId/trace",
            lazy: async () => {
              const module = await import("@/pages/RunTracePage");
              return { Component: module.RunTracePage };
            },
          },
          {
            path: "runs/:runId/evidence",
            lazy: async () => {
              const module = await import("@/pages/RunEvidencePage");
              return { Component: module.RunEvidencePage };
            },
          },
          {
            path: "compare",
            lazy: async () => {
              const module = await import("@/pages/app/ComparePage");
              return { Component: module.ComparePage };
            },
          },
          {
            path: "watch",
            lazy: async () => {
              const module = await import("@/pages/app/WatchPage");
              return { Component: module.WatchPage };
            },
          },
          {
            path: "templates",
            lazy: async () => {
              const module = await import("@/pages/app/TemplatesPage");
              return { Component: module.TemplatesPage };
            },
          },
          {
            path: "settings",
            lazy: async () => {
              const module = await import("@/pages/app/SettingsPage");
              return { Component: module.SettingsPage };
            },
          },
          {
            path: "settings/skill-admin",
            lazy: async () => {
              const module = await import("@/pages/SkillStagingPage");
              return { Component: module.SkillStagingPage };
            },
          },
          {
            path: "*",
            element: <NotFoundPage />,
          },
        ],
      },
      {
        path: "runs/new",
        element: <Navigate replace to="/app/runs/new" />,
      },
      {
        path: "runs/:runId",
        loader: ({ params }) => redirect(`/app/runs/${params.runId ?? ""}`),
      },
      {
        path: "runs/:runId/trace",
        loader: ({ params }) => redirect(`/app/runs/${params.runId ?? ""}/trace`),
      },
      {
        path: "runs/:runId/evidence",
        loader: ({ params }) => redirect(`/app/runs/${params.runId ?? ""}/evidence`),
      },
      {
        path: "skills/staging",
        element: <Navigate replace to="/app/settings/skill-admin" />,
      },
      {
        path: "*",
        element: <NotFoundPage />,
      },
    ],
  },
]);
