import { redirect } from "next/navigation";
import { getCurrentUserServer } from "@/lib/server-api";
import { AuthPageLayout } from "@/components/auth/AuthPageLayout";
import { LoginForm } from "@/components/auth/LoginForm";

export const metadata = { title: "Sign in · AI Commerce OS" };

export default async function LoginPage() {
  const user = await getCurrentUserServer();
  if (user) {
    redirect("/dashboard");
  }

  return (
    <AuthPageLayout title="Sign in" subtitle="Welcome back to AI Commerce OS.">
      <LoginForm />
    </AuthPageLayout>
  );
}
