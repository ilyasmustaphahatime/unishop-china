import { Link } from 'react-router';
import Card from '../../components/common/Card';
import ProductForm from '../../components/products/ProductForm';

export default function AddProductPage() {
  return <section className="mx-auto max-w-2xl">
    <h1 className="text-3xl font-black">Create a listing</h1>
    <p className="my-4 text-slate-600">Verified sellers can create drafts after completing onboarding and verifying email and phone. Publishing is a separate action.</p>
    <Link className="text-red-700 underline" to="/seller/verification">Seller verification</Link>
    <Card className="mt-5 p-6"><ProductForm /></Card>
  </section>;
}
