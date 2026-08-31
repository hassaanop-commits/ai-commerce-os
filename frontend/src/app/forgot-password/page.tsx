import { AuthPageLayout } from "@/components/auth/AuthPageLayout";
import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";

export const metadata = { title: "Forgot password · AI Commerce OS" };

export default function ForgotPasswordPage() {
  return (
    <AuthPageLayout title="Reset your password" subtitle="We'll email you a link to get back in.">
      <ForgotPasswordForm />
    </AuthPageLayout>
  );
}
