// Registers the desk's English dictionary before any desk component renders.
import '../legal/i18n';
import { useAuth } from '../contexts/AuthContext';
import LegalAccessGate from '../components/LegalAccessGate';
import LegalDesk from '../legal/LegalDesk';

export default function ContractReview() {
  const { user, logout } = useAuth();
  return <LegalAccessGate><LegalDesk user={user} logout={logout} /></LegalAccessGate>;
}
