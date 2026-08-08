import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an unexpected error:", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 rounded-2xl bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/40 text-stone-900 dark:text-stone-100 max-w-xl mx-auto my-8 font-sans shadow-md">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-8 h-8 rounded-full bg-red-100 dark:bg-red-900/50 text-red-600 dark:text-red-400 flex items-center justify-center font-bold text-sm">
              ⚠
            </span>
            <h3 className="font-mono text-lg font-bold text-red-900 dark:text-red-200">
              Something went wrong
            </h3>
          </div>
          <p className="text-xs text-red-700 dark:text-red-300 mb-4 leading-relaxed font-mono">
            {this.state.error?.message || "An unexpected UI error occurred."}
          </p>
          <button
            onClick={this.handleReset}
            className="px-4 py-2 text-xs font-semibold bg-red-600 hover:bg-red-700 text-white rounded-xl shadow-xs transition-colors cursor-pointer"
          >
            Reload View
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
