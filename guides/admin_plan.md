# Admin Dashboard Implementation Plan

## Context
Aakashvani is a multi-tenant AI outbound calling platform. The backend is complete and the client SPA is done. The current focus is building the **Admin Dashboard** component of the React/Next.js SPA. The design must adhere strictly to the "Electric Professional" design system (Dual Theme: Arctic Signal & Molten Studio) outlined in `guides/design.md`.

## Goal
Implement 6 admin pages based on user-provided code snippets without making major design changes, while wiring them up to the backend according to the technical expectations.

## 6 Target Pages
1. **Login Page (`/admin/login`)**: Single input for admin API key.
2. **Global Overview (`/admin`)**: System health and high-level stats.
3. **Clients List (`/admin/clients`)**: Manage clients, view table, create new client (one-time API key display), suspend clients.
4. **Client Detail & Billing (`/admin/clients/:id`)**: Client overview, billing ledger, webhook management, manual credit adjustment.
5. **Bot Configurations (`/admin/bot-configs`)**: View/edit existing bots, create new bots from available scripts.
6. **Global Calls & Emergency Overrides (`/admin/calls`)**: Global call feed and emergency campaign stops/cancels.

## Execution Strategy
1. **Receive Code Snippets**: Wait for the user to provide the code snippet for each page.
2. **Analyze Snippet**: Review the provided design and functionality.
3. **Wire to Backend**: 
   - Integrate the Axios/fetch wrappers (e.g., `src/api/admin.ts`).
   - Add state management for API calls (loading states, data fetching, mutations).
   - Hook up pagination, error handling, and polling where applicable.
4. **Preserve Design**: Ensure the provided aesthetic, tailwind classes, and UI components are kept intact, as requested ("no big changes to the design").
5. **Iterate**: Complete this for all 6 pages as they are provided.

## Next Steps
- Waiting for the user to paste the code snippet for the first page.
