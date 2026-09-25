import { useAuth } from '../contexts/AuthContext';
import LegalAccessGate from '../components/LegalAccessGate';
import LegalDesk from '../legal/LegalDesk';
import './ContractReview.css';

export default function ContractReview() {
  const { user, logout } = useAuth();
  return <LegalAccessGate><LegalDesk user={user} logout={logout} /></LegalAccessGate>;
}
