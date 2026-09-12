import React from "react";

/** Catches render crashes per-route and shows the message in-page
 * instead of a blank screen. */
export default class RouteErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch() {
    this.setState((prev) =>
      prev.error ? prev : { ...prev }
    );
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-2xl border border-red-300 bg-red-50 p-5">
          <h2 className="font-extrabold text-red-800">This view crashed</h2>
          <p className="mt-1 font-mono text-xs text-red-700">
            {String(this.state.error.message || this.state.error)}
          </p>
          <p className="mt-2 text-xs text-red-600">
            Screenshot this and share it to get it fixed.
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}
