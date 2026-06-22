import 'package:flutter/material.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Flutter Assignment',
      theme: ThemeData(
        primarySwatch: Colors.indigo,
        scaffoldBackgroundColor: Colors.grey[100],
      ),
      home: const AssignmentScreen(),
    );
  }
}

class AssignmentScreen extends StatelessWidget {
  const AssignmentScreen({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    // Getting full screen width for Question 2
    double screenWidth = MediaQuery.of(context).size.width;

    return Scaffold(
      // ==========================================
      // QUESTION 1: AppBar Configuration
      // ==========================================
      appBar: AppBar(
        title: const Text(
          'Flutter Assignment - Colors & Shapes',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
        backgroundColor: Colors.indigo,
        elevation: 4,
      ),
      
      // SingleChildScrollView ensures everything scrolls perfectly together
      body: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            
            // ==========================================
            // QUESTION 2: Container with Name & Reg No
            // ==========================================
            Container(
              width: screenWidth, // Matches the width of the interface
              height: 120,
              margin: const EdgeInsets.all(16.0), // External spacing
              padding: const EdgeInsets.all(16.0), // Internal spacing
              alignment: Alignment.center, // Center alignment property
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12.0), // BorderRadius
                border: Border.all(color: Colors.indigo, width: 2), // Border
                boxShadow: [
                  BoxShadow(
                    color: Colors.grey.withOpacity(0.5),
                    spreadRadius: 2,
                    blurRadius: 5,
                    offset: const Offset(0, 3), // BoxShadow
                  ),
                ],
              ),
              child: Text(
                'Name: Aakila Samadh\nRegistration No: 03241075',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: Colors.indigo,
                ),
              ),
            ),

            const Divider(thickness: 2, color: Colors.grey),

            // ==========================================
            // QUESTION 3: Grid of 12 Circles Layout
            // ==========================================
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    "Question 3: Grid of 12 Circles",
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 10),
                  
                  // Main Column containing 3 Rows
                  Column(
                    children: [
                      // Row 1
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                        children: [
                          _buildCircleAvatar(Colors.red, "Red"),
                          _buildCircleAvatar(Colors.pink, "Pink"),
                          _buildCircleAvatar(Colors.purple, "Purple"),
                          _buildCircleAvatar(Colors.deepPurple, "DPurple"),
                        ],
                      ),
                      const SizedBox(height: 15), // SizedBox between Rows
                      
                      // Row 2
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                        children: [
                          _buildCircleAvatar(Colors.blue, "Blue"),
                          _buildCircleAvatar(Colors.cyan, "Cyan"),
                          _buildCircleAvatar(Colors.teal, "Teal"),
                          _buildCircleAvatar(Colors.green, "Green"),
                        ],
                      ),
                      const SizedBox(height: 15), // SizedBox between Rows
                      
                      // Row 3
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                        children: [
                          _buildCircleAvatar(Colors.amber, "Amber"),
                          _buildCircleAvatar(Colors.orange, "Orange"),
                          _buildCircleAvatar(Colors.deepOrange, "DOrange"),
                          _buildCircleAvatar(Colors.brown, "Brown"),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
            ),

            const Divider(thickness: 2, color: Colors.grey),

            // ==========================================
            // QUESTION 4: Stack Layout (Overlapping Layers)
            // ==========================================
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    "Question 4: Stack Layout",
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 10),
                  
                  // Center the Stack for clean presentation
                  Center(
                    child: SizedBox(
                      width: 300,
                      height: 300,
                      child: Stack(
                        children: [
                          // 1. Largest Container (Bottom Layer)
                          Container(
                            width: 300,
                            height: 300,
                            decoration: const BoxDecoration(
                              color: Colors.amber, // Distinct color 1
                            ),
                          ),
                          
                          // 2. Large Container (Middle Layer)
                          Positioned(
                            top: 25,
                            left: 25,
                            child: Container(
                              width: 200,
                              height: 200,
                              decoration: const BoxDecoration(
                                color: Colors.orange, // Distinct color 2
                              ),
                            ),
                          ),
                          
                          // 3. Small Container (Top Layer)
                          Positioned(
                            top: 50,
                            left: 50,
                            child: Container(
                              width: 100,
                              height: 100,
                              alignment: Alignment.center, // Alignment Property
                              decoration: const BoxDecoration(
                                color: Colors.red, // Distinct color 3
                              ),
                              child: const Text(
                                'Stack Text',
                                style: TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),

            const Divider(thickness: 2, color: Colors.grey),

            // ==========================================
            // QUESTION 5: Tappable Card Widget
            // ==========================================
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    "Question 5: Material Design Card",
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 10),
                  
                  // Card implementation wrapped with InkWell for tappable feedback
                  Card(
                    elevation: 6.0, // Elevation depth shadow
                    margin: const EdgeInsets.symmetric(vertical: 8.0), // External margin
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16.0), // Corner radius shape
                    ),
                    clipBehavior: Clip.antiAlias, // Clip behavior handles rounded image corners
                    child: InkWell(
                      onTap: () {
                        // Action when card is tapped
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Card Tapped!')),
                        );
                      },
                      child: Padding(
                        padding: const EdgeInsets.all(16.0), // Consistent internal padding
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Placeholder representing an Image or Banner
                            Container(
                              height: 120,
                              width: double.infinity,
                              color: Colors.indigo[200],
                              child: const Icon(Icons.image, size: 50, color: Colors.white),
                            ),
                            const SizedBox(height: 12),
                            // Distinct Text Styles for hierarchy
                            const Text(
                              'Primary Title Information',
                              style: TextStyle(
                                fontSize: 20,
                                fontWeight: FontWeight.bold,
                                color: Colors.black87,
                              ),
                            ),
                            const SizedBox(height: 6),
                            const Text(
                              'Secondary descriptive text providing further details regarding the app elements.',
                              style: TextStyle(
                                fontSize: 14,
                                color: Colors.grey,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 30), // Bottom breathing room
          ],
        ),
      ),
    );
  }

  // Helper builder widget for Question 3 Circles
  Widget _buildCircleAvatar(Color color, String label) {
    return Column(
      children: [
        Container(
          width: 60,
          height: 60,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle, // Specified BoxShape
          ),
          alignment: Alignment.center,
          child: Text(
            label[0], // First letter matching app context/theme text
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        const SizedBox(height: 4),
        Text(label, style: const TextStyle(fontSize: 11)),
      ],
    );
  }
}