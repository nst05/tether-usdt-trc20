import { ListingForm } from "@/components/listing-form";

export default function NewListingPage() {
  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold">Разместить технику</h1>
      <p className="mb-6 text-sm text-gray-500">
        Заполните карточку техники — она появится в каталоге сразу после
        публикации.
      </p>
      <ListingForm />
    </div>
  );
}
