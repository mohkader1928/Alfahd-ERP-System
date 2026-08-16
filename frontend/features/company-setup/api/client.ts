import { apiClient } from "@/lib/api-client";
import type {
  CompanyProfile,
  CompanyProfileWriteInput,
  ConfigurationPlan,
  CustomerAssessment,
  ErpBlueprint,
  SizingResult,
} from "./types";

const BASE = "/api/v1/company-profile";

export const companySetupApi = {
  getProfile: (companyId: string) => apiClient.get<CompanyProfile>(`${BASE}`, { companyId }),

  createProfile: (companyId: string, payload: CompanyProfileWriteInput) =>
    apiClient.post<CompanyProfile>(`${BASE}`, payload, { companyId }),

  updateProfile: (companyId: string, payload: CompanyProfileWriteInput) =>
    apiClient.patch<CompanyProfile>(`${BASE}`, payload, { companyId }),

  computeSizing: (companyId: string) => apiClient.post<SizingResult>(`${BASE}/sizing`, undefined, { companyId }),

  getLatestSizing: (companyId: string) => apiClient.get<SizingResult>(`${BASE}/sizing/latest`, { companyId }),

  generateBlueprint: (companyId: string) =>
    apiClient.post<ErpBlueprint>(`${BASE}/blueprint`, undefined, { companyId }),

  getLatestBlueprint: (companyId: string) => apiClient.get<ErpBlueprint>(`${BASE}/blueprint/latest`, { companyId }),

  getBlueprint: (companyId: string, blueprintId: string) =>
    apiClient.get<ErpBlueprint>(`${BASE}/blueprint/${blueprintId}`, { companyId }),

  approveBlueprint: (companyId: string, blueprintId: string) =>
    apiClient.post<ErpBlueprint>(`${BASE}/blueprint/${blueprintId}/approve`, undefined, { companyId }),

  createConfigurationPlan: (companyId: string) =>
    apiClient.post<ConfigurationPlan>(`${BASE}/configuration-plan`, undefined, { companyId }),

  validateConfigurationPlan: (companyId: string, planId: string) =>
    apiClient.post<ConfigurationPlan>(`${BASE}/configuration-plan/${planId}/validate`, undefined, { companyId }),

  applyConfigurationPlan: (companyId: string, planId: string) =>
    apiClient.post<ConfigurationPlan>(`${BASE}/configuration-plan/${planId}/apply`, undefined, { companyId }),

  getConfigurationPlan: (companyId: string, planId: string) =>
    apiClient.get<ConfigurationPlan>(`${BASE}/configuration-plan/${planId}`, { companyId }),

  getAssessment: (companyId: string) => apiClient.get<CustomerAssessment>(`${BASE}/assessment`, { companyId }),
};
