export interface OrganizationMembership {
  organization_id: string;
  name: string;
  slug: string;
  role_key: string;
  role_name: string;
  joined_at: string | null;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
}
