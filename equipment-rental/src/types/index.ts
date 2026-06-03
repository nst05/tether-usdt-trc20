export interface Equipment {
  id: string;
  name: string;
  category: string;
  subcategory: string;
  image: string;
  specs: Record<string, string>;
  pricePerDay: number;
  pricePerWeek: number;
  pricePerMonth: number;
  availability: 'available' | 'rented' | 'maintenance';
  location: string;
  rating: number;
  reviewCount: number;
  description: string;
  features: string[];
  weight: number;
  power: string;
  tags: string[];
}

export interface Order {
  id: string;
  equipmentId: string;
  equipmentName: string;
  clientName: string;
  clientEmail: string;
  clientPhone: string;
  clientCompany?: string;
  startDate: string;
  endDate: string;
  totalPrice: number;
  status: 'pending' | 'confirmed' | 'active' | 'completed' | 'cancelled';
  createdAt: string;
  notes?: string;
}

export interface CartItem {
  equipment: Equipment;
  startDate: string;
  endDate: string;
  days: number;
  totalPrice: number;
}

export interface WizardData {
  projectType: string;
  area: string;
  volume: string;
  startDate: string;
  endDate: string;
  terrain: string;
  access: string;
  budget: string;
}

export interface RecommendedPackage {
  equipment: Equipment;
  reason: string;
  quantity: number;
  days: number;
  subtotal: number;
}

export interface Client {
  id: string;
  name: string;
  email: string;
  phone: string;
  company?: string;
  orders: Order[];
  totalSpent: number;
  createdAt: string;
}
