import UIKit

// MARK: - Token Refresh

extension SubscriptionsViewController {
    func observeTokenRefresh() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleTokenRefresh),
            name: .tokenDidRefresh,
            object: nil
        )
    }

    @objc
    func handleTokenRefresh() {
        AppLog.subs("token refreshed → reloading feed")
        loadInitialContent()
    }
}
