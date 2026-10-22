import { useEffect, useMemo } from "react";
import { ClerkProvider, SignIn, SignUp, UserButton, useSession } from "@clerk/react";
import { Files } from "lucide-react";
import App from "./App";
import { createApiClient } from "./api";

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

function AccountWorkspace() {
  const { isLoaded, session } = useSession();
  const isSignUp = window.location.pathname.startsWith("/sign-up");
  const api = useMemo(
    () =>
      session
        ? createApiClient(async () => {
            if (session.status !== "active") return null;
            const token = await session.getToken();
            return session.status === "active" ? token : null;
          })
        : null,
    [session],
  );
  useEffect(() => () => api?.abortRequests(), [api]);
  if (!isLoaded)
    return (
      <div className="auth-page" role="status">
        Opening your workspace…
      </div>
    );
  if (!session || session.status !== "active" || !api) {
    return (
      <main className="auth-page">
        <div className="auth-brand">
          <Files size={27} />
          <span>axelyn.</span>
        </div>
        <p className="auth-intro">Sign in to your workspace.</p>
        {isSignUp ? (
          <SignUp routing="hash" signInUrl="/" forceRedirectUrl="/" />
        ) : (
          <SignIn routing="hash" signUpUrl="/sign-up" forceRedirectUrl="/" />
        )}
      </main>
    );
  }
  return <App key={session.id} api={api} accountMenu={<UserButton />} />;
}

export default function AuthRoot() {
  if (!PUBLISHABLE_KEY)
    return (
      <main className="auth-page">
        <div className="auth-brand">
          <Files size={27} />
          <span>axelyn.</span>
        </div>
        <h1>Sign-in is unavailable</h1>
        <p>Please contact your workspace administrator.</p>
      </main>
    );
  return (
    <ClerkProvider
      publishableKey={PUBLISHABLE_KEY}
      appearance={{
        variables: {
          colorPrimary: "#7856a8",
          colorBackground: "#ffffff",
          colorForeground: "#3c3247",
          colorMutedForeground: "#9682a4",
          colorInput: "#fcfaff",
          colorPrimaryForeground: "#ffffff",
          colorNeutral: "#3c3247",
          colorInputForeground: "#3c3247",
          borderRadius: "0.6rem",
        },
      }}
    >
      <AccountWorkspace />
    </ClerkProvider>
  );
}
