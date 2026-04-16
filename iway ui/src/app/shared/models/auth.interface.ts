export interface LoginRequest {
  matricule: string;
  password: string;
}

export type UserRole = 'Adherent' | 'Prestataire' | 'Agent' | 'Admin';

export interface User {
  matricule: string;
  nom: string;
  prenom: string;
  role: UserRole;
  email?: string;
  specialite?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}
