import { SignUp } from '@clerk/nextjs';

export default function Page() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-purple-600 to-indigo-700">
      <SignUp />
    </div>
  );
}
