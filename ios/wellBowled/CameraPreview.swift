import SwiftUI
import AVFoundation
import UIKit

struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession
    
    func makeUIView(context: Context) -> UIView {
        let view = UIView(frame: .zero)
        let previewLayer = AVCaptureVideoPreviewLayer(session: session)
        previewLayer.videoGravity = .resizeAspectFill
        
        // Handle mirroring for front camera (Standard UX)
        if let connection = previewLayer.connection, connection.isVideoMirroringSupported {
            // Check if using front camera
            let isFront = session.inputs.compactMap { $0 as? AVCaptureDeviceInput }
                .contains { $0.device.position == .front }
                
            if connection.automaticallyAdjustsVideoMirroring {
                connection.automaticallyAdjustsVideoMirroring = false
            }
            connection.isVideoMirrored = isFront
        }
        
        view.layer.addSublayer(previewLayer)
        
        DispatchQueue.main.async {
            previewLayer.frame = view.bounds
        }
        return view
    }
    
    func updateUIView(_ uiView: UIView, context: Context) {
        if let layer = uiView.layer.sublayers?.first as? AVCaptureVideoPreviewLayer {
            layer.frame = uiView.bounds
            
            // Re-evaluate mirroring (e.g. after camera flip)
            if let connection = layer.connection, connection.isVideoMirroringSupported {
                let isFront = session.inputs.compactMap { $0 as? AVCaptureDeviceInput }
                    .contains { $0.device.position == .front }
                if connection.automaticallyAdjustsVideoMirroring {
                    connection.automaticallyAdjustsVideoMirroring = false
                }
                connection.isVideoMirrored = isFront
            }
        }
    }
}
