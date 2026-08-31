import { redirect } from "next/navigation";
import { getCurrentUserServer } from "@/lib/server-api";
import { AuthPageLayout } from "@/components/auth/AuthPageLayout";
import { SignupForm } from "@/components/auth/SignupForm";

export const metadata = { title: "Create your account · AI Commerce OS" };

export default async function SignupPage() {
  const user = await getCurrentUserServer();
  if (user) {
    redirect("/dashboard");
  }

  return (
    <AuthPageLayout
      title="Create your account"
      subtitle="Start running your commerce operations with AI Commerce OS."
    >
      <SignupForm />
    </AuthPageLayout>
  );
}
